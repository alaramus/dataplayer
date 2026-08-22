# Рабочая область и движок панелей — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** заменить модальный `CatalogDialog` рабочей областью из панелей с изменяемыми границами, вкладками и перетаскиванием, построенной на собственном движке, который ничего не знает о предметной области.

**Architecture:** движок в `src/shared/workspace/` держит дерево раскладки как размеченный союз и меняет его только чистыми функциями; компоненты движка получают всё через один инъектируемый контекст и никогда не видят тип панели. Фича в `src/features/workspace/` объявляет союз `Panel`, реестр видов панелей и раскладку по умолчанию.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Quasar, Pinia, `@tanstack/vue-query`, zod 4, Vitest, `@vue/test-utils`, Playwright.

## Global Constraints

- Спека: `docs/superpowers/specs/2026-08-22-workspace-design.md`. Правила: `ENGINEERING.md`.
- Всё в репозитории по-английски: код, комментарии, строки интерфейса, имена тестов, сообщения коммитов. Русский только в `docs/superpowers/`.
- TDD: сначала падающий тест, затем реализация. Прогон теста и чтение вывода обязательны — «должно работать» не считается.
- Рабочий каталог всех команд — `frontend/`. Запуск: `bun run test:unit`, `bun run lint`, `bun run type-check`, `bunx playwright test`.
- `bun run type-check` требует настоящий Node, не bun. На Windows `.cmd`-обёртка это делает сама.
- `src/client` порождается из OpenAPI и руками не правится.
- Вне `src/shared/ui` запрещены `q-dialog`, `q-card`, `q-card-section`, `q-card-actions`, `q-btn`, `q-tooltip`, `q-banner`, `q-input`, `q-select`, `q-toggle`, `q-file`, `q-table`, `q-badge`, `q-spinner` в обоих написаниях, и запрещён `useQuasar`. Правило — `eslint.config.js`, проверяется `bun run lint`. В `shared/workspace` не должно быть ни одного `q-*`.
- Pinia не импортирует `@/client` и `@/features/*` (правило ESLint для `src/stores/**`).
- Именование, общее для всех задач: `LayoutNode`, `SplitNode`, `LeafNode`, `Path`, `PanelId`, `NodeId`, `DropZone`, `MIN_PANEL_PX = 120`, `COLLAPSED_PX = 28`.
- Файлы движка не должны знать слов «connector», «catalog», «rows».
- Ветка `dataPlayer`. Коммит после каждой задачи, сообщение по-английски, с `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

# Этап A — движок

## Задача 1: модель раскладки и адресация узлов

**Files:**
- Create: `frontend/src/shared/workspace/model.ts`
- Create: `frontend/src/shared/workspace/tree.ts`
- Test: `frontend/src/shared/workspace/tree.spec.ts`

**Interfaces:**
- Consumes: ничего.
- Produces: типы `LayoutNode`, `SplitNode`, `LeafNode`, `PanelId`, `NodeId`, `Path`, `DropZone`; константы `MIN_PANEL_PX`, `COLLAPSED_PX`; конструкторы `makeLeaf(id, panels, activePanel?)`, `makeSplit(id, direction, children, sizes)`; функции `nodeAt(root, path)`, `pathOfNode(root, nodeId)`, `pathOfPanel(root, panelId)`, `leavesOf(root)`.

- [ ] **Step 1: Write the failing test**

`frontend/src/shared/workspace/tree.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { makeLeaf, makeSplit } from "./model"
import { leavesOf, nodeAt, pathOfNode, pathOfPanel } from "./tree"

const sample = () =>
  makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2", "p3"])], [30, 70])

describe("addressing a node", () => {
  it("finds the root by the empty path", () => {
    const tree = sample()
    expect(nodeAt(tree, [])).toBe(tree)
  })

  it("finds a child by its index", () => {
    expect(nodeAt(sample(), [1])?.id).toBe("b")
  })

  it("answers null for a path that leads nowhere", () => {
    expect(nodeAt(sample(), [5])).toBeNull()
  })

  it("finds the path of a node by its id", () => {
    expect(pathOfNode(sample(), "b")).toEqual([1])
  })

  it("finds the path of the leaf holding a panel", () => {
    expect(pathOfPanel(sample(), "p3")).toEqual([1])
  })

  it("answers null for a panel nobody holds", () => {
    expect(pathOfPanel(sample(), "nope")).toBeNull()
  })

  it("lists every leaf in order", () => {
    expect(leavesOf(sample()).map((leaf) => leaf.id)).toEqual(["a", "b"])
  })
})

describe("a leaf", () => {
  it("makes its first panel the active one by default", () => {
    expect(makeLeaf("a", ["p1", "p2"]).activePanel).toBe("p1")
  })

  it("refuses to be built with no panels at all", () => {
    expect(() => makeLeaf("a", [])).toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: FAIL — `Failed to resolve import "./model"`.

- [ ] **Step 3: Write model.ts**

`frontend/src/shared/workspace/model.ts`:

```ts
/**
 * The layout of the workspace: a tree of sections, and nothing about what
 * they show.
 *
 * A panel is referred to by id only. What a panel is belongs to the feature
 * that uses the engine — see docs/superpowers/specs/2026-08-22-workspace-design.md.
 */

export type PanelId = string
export type NodeId = string

/** The position of a node: the index to take at every level from the root. */
export type Path = number[]

export type Direction = "row" | "column"

/** Where a dragged panel would land, relative to the section under it. */
export type DropZone = "left" | "right" | "top" | "bottom" | "center"

export interface LeafNode {
  kind: "leaf"
  id: NodeId
  panels: PanelId[]
  activePanel: PanelId
  collapsed: boolean
}

export interface SplitNode {
  kind: "split"
  id: NodeId
  direction: Direction
  children: LayoutNode[]
  /** Percentages, one per child, summing to 100. */
  sizes: number[]
}

export type LayoutNode = SplitNode | LeafNode

/** The smallest a section may be dragged to. Percentages cannot say this. */
export const MIN_PANEL_PX = 120

/** What a collapsed section leaves behind: enough for the handle and no more. */
export const COLLAPSED_PX = 28

export function makeLeaf(id: NodeId, panels: PanelId[], activePanel?: PanelId): LeafNode {
  const [first] = panels
  // A section with nothing in it is not a thing that can be built: it is a
  // state normalize() repairs. Refusing it here is what lets activePanel be a
  // PanelId rather than a PanelId that might be missing.
  if (first === undefined) throw new Error(`A leaf needs at least one panel: ${id}`)
  return {
    kind: "leaf",
    id,
    panels,
    activePanel: activePanel ?? first,
    collapsed: false,
  }
}

export function makeSplit(
  id: NodeId,
  direction: Direction,
  children: LayoutNode[],
  sizes: number[]
): SplitNode {
  return { kind: "split", id, direction, children, sizes }
}

let counter = 0

/** Ids are only ever compared, never parsed, so a counter is enough. */
export function nextId(prefix: string): string {
  counter += 1
  return `${prefix}-${String(counter)}`
}
```

- [ ] **Step 4: Write the addressing half of tree.ts**

`frontend/src/shared/workspace/tree.ts`:

```ts
/**
 * Every change to the layout is a pure function: it takes a tree and returns a
 * new one. Nodes carry no reference to their parent, so a node is addressed by
 * the path that reaches it.
 *
 * The old application mutated nodes in place and kept parent back-pointers,
 * which is why it needed a history of layouts and a command language to undo
 * anything. See the spec, W3.
 */

import type { LayoutNode, LeafNode, NodeId, PanelId, Path } from "./model"

export function nodeAt(root: LayoutNode, path: Path): LayoutNode | null {
  let node: LayoutNode = root
  for (const index of path) {
    if (node.kind !== "split") return null
    const child = node.children[index]
    if (child === undefined) return null
    node = child
  }
  return node
}

export function pathOfNode(root: LayoutNode, nodeId: NodeId): Path | null {
  if (root.id === nodeId) return []
  if (root.kind !== "split") return null
  for (const [index, child] of root.children.entries()) {
    const inner = pathOfNode(child, nodeId)
    if (inner !== null) return [index, ...inner]
  }
  return null
}

export function pathOfPanel(root: LayoutNode, panelId: PanelId): Path | null {
  if (root.kind === "leaf") return root.panels.includes(panelId) ? [] : null
  for (const [index, child] of root.children.entries()) {
    const inner = pathOfPanel(child, panelId)
    if (inner !== null) return [index, ...inner]
  }
  return null
}

export function leavesOf(root: LayoutNode): LeafNode[] {
  if (root.kind === "leaf") return [root]
  return root.children.flatMap(leavesOf)
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: PASS, 9 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/workspace/model.ts frontend/src/shared/workspace/tree.ts frontend/src/shared/workspace/tree.spec.ts
git commit -m "feat(workspace): a layout is a tree of sections addressed by path"
```

---

## Задача 2: нормализация и замена узла

**Files:**
- Modify: `frontend/src/shared/workspace/tree.ts`
- Modify: `frontend/src/shared/workspace/tree.spec.ts`

**Interfaces:**
- Consumes: `nodeAt`, `pathOfNode` из задачи 1.
- Produces: `replaceAt(root, path, node)` где `node: LayoutNode | null` (null удаляет), `normalize(root)`. Обе возвращают новое дерево; `replaceAt` не нормализует, `normalize` вызывается всеми операциями задачи 3.

- [ ] **Step 1: Write the failing test**

Дописать в `frontend/src/shared/workspace/tree.spec.ts`:

```ts
import { normalize, replaceAt } from "./tree"

describe("replacing a node", () => {
  it("puts a new node in place of the old one and leaves the original alone", () => {
    const tree = sample()
    const next = replaceAt(tree, [0], makeLeaf("z", ["p9"]))
    expect((next as SplitNode).children[0].id).toBe("z")
    expect((tree as SplitNode).children[0].id).toBe("a")
  })

  it("removes the child the path names, not whichever one is easiest", () => {
    const next = replaceAt(sample(), [0], null) as SplitNode
    expect(next.children).toHaveLength(1)
    // Asserting the length alone would pass against removing the wrong index.
    expect(next.children[0]?.id).toBe("b")
    expect(next.sizes).toEqual([70])
  })

  it("answers null when the whole tree is removed", () => {
    expect(replaceAt(makeLeaf("a", ["p1"]), [], null)).toBeNull()
  })
})

describe("normalising a tree", () => {
  it("brings the sizes of a split back to a hundred", () => {
    const odd = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [10, 30])
    const sizes = (normalize(odd) as SplitNode).sizes
    expect(sizes[0]).toBeCloseTo(25)
    expect(sizes[1]).toBeCloseTo(75)
  })

  it("replaces a split holding one child with that child", () => {
    const lonely = makeSplit("root", "row", [makeLeaf("a", ["p1"])], [100])
    expect(normalize(lonely)?.id).toBe("a")
  })

  it("drops a leaf that holds no panels", () => {
    const empty = makeSplit("root", "row", [emptyLeaf("a"), makeLeaf("b", ["p2"])], [50, 50])
    expect(normalize(empty)?.id).toBe("b")
  })

  it("flattens a nested split of the same direction into its parent", () => {
    const nested = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit("inner", "row", [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])], [50, 50]),
      ],
      [50, 50]
    )
    const flat = normalize(nested) as SplitNode
    expect(flat.children.map((child) => child.id)).toEqual(["a", "b", "c"])
    expect(flat.sizes.map(Math.round)).toEqual([50, 25, 25])
  })

  it("leaves a nested split of the other direction alone", () => {
    const nested = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit("inner", "column", [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])], [50, 50]),
      ],
      [50, 50]
    )
    expect((normalize(nested) as SplitNode).children[1].kind).toBe("split")
  })

  it("keeps the active panel pointing at a panel the leaf still holds", () => {
    const stale: LeafNode = { kind: "leaf", id: "a", panels: ["p1"], activePanel: "gone", collapsed: false }
    expect((normalize(stale) as LeafNode).activePanel).toBe("p1")
  })

  it("answers null when nothing is left", () => {
    expect(normalize(emptyLeaf("a"))).toBeNull()
  })
})
```

Дополнить импорт типов сверху файла:

```ts
import type { LeafNode, SplitNode } from "./model"
```

и добавить рядом с `sample` конструктор недопустимого листа — `makeLeaf` его
построить отказывается, и это правильно: пустой лист не создают, его чинят.

```ts
/** A leaf with no panels: not something makeLeaf builds, but what normalize repairs. */
const emptyLeaf = (id: string): LeafNode => ({
  kind: "leaf",
  id,
  panels: [],
  activePanel: "",
  collapsed: false,
})
```

`normalize` возвращает `LayoutNode | null`, поэтому обращения к результату в
тестах идут через `?.`.

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: FAIL — `replaceAt is not exported`.

- [ ] **Step 3: Implement**

Дописать в `frontend/src/shared/workspace/tree.ts`:

```ts
import { makeSplit } from "./model"

/**
 * Put `node` where `path` points, or remove what is there when `node` is null.
 *
 * Nothing is normalised here: the caller performs one edit and then calls
 * normalize once, so a tree is never observed half-changed.
 */
export function replaceAt(
  root: LayoutNode,
  path: Path,
  node: LayoutNode | null
): LayoutNode | null {
  if (path.length === 0) return node
  if (root.kind !== "split") return root

  const [index, ...rest] = path
  const child = root.children[index]
  if (child === undefined) return root

  const replacement = replaceAt(child, rest, node)
  const children = [...root.children]
  const sizes = [...root.sizes]

  if (replacement === null) {
    children.splice(index, 1)
    sizes.splice(index, 1)
  } else {
    children[index] = replacement
  }

  if (children.length === 0) return null
  return makeSplit(root.id, root.direction, children, sizes)
}

/**
 * Bring a tree to its canonical shape.
 *
 * Called after every edit, so no other function has to worry about an empty
 * leaf, a split of one, or sizes that no longer add up. The old application
 * had none of this, which is why it needed sections marked `fake` to stand in
 * for nodes it could not remove.
 */
export function normalize(root: LayoutNode): LayoutNode | null {
  if (root.kind === "leaf") {
    if (root.panels.length === 0) return null
    if (root.panels.includes(root.activePanel)) return root
    return { ...root, activePanel: root.panels[0] }
  }

  const children: LayoutNode[] = []
  const sizes: number[] = []

  for (const [index, child] of root.children.entries()) {
    const kept = normalize(child)
    if (kept === null) continue
    const size = root.sizes[index] ?? 0
    // A nested split running the same way is the same set of borders drawn
    // twice: its children join the parent, sharing the slot it occupied.
    if (kept.kind === "split" && kept.direction === root.direction) {
      const total = kept.sizes.reduce((sum, value) => sum + value, 0) || 1
      for (const [innerIndex, inner] of kept.children.entries()) {
        children.push(inner)
        sizes.push((size * (kept.sizes[innerIndex] ?? 0)) / total)
      }
      continue
    }
    children.push(kept)
    sizes.push(size)
  }

  if (children.length === 0) return null
  if (children.length === 1) return children[0]

  const total = sizes.reduce((sum, value) => sum + value, 0)
  const scaled =
    total > 0 ? sizes.map((value) => (value * 100) / total) : sizes.map(() => 100 / sizes.length)

  return makeSplit(root.id, root.direction, children, scaled)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: PASS, 17 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/workspace/tree.ts frontend/src/shared/workspace/tree.spec.ts
git commit -m "feat(workspace): one normalisation, run after every edit"
```

---

## Задача 3: операции над панелями и размерами

**Files:**
- Modify: `frontend/src/shared/workspace/tree.ts`
- Modify: `frontend/src/shared/workspace/tree.spec.ts`

**Interfaces:**
- Consumes: `replaceAt`, `normalize`, `pathOfPanel`, `pathOfNode`, `nodeAt` из задач 1–2.
- Produces:
  - `addPanel(root, leafId, panelId): LayoutNode`
  - `removePanel(root, panelId): LayoutNode | null`
  - `activatePanel(root, panelId): LayoutNode`
  - `setCollapsed(root, leafId, collapsed): LayoutNode`
  - `resizeSplit(root, splitId, index, delta, minPercent): LayoutNode` — `index` это номер границы между `children[index]` и `children[index + 1]`, `delta` и `minPercent` в процентах
  - `splitLeaf(root, leafId, panelId, zone, newLeafId): LayoutNode`
  - `movePanel(root, panelId, targetLeafId, zone, newLeafId): LayoutNode`

- [ ] **Step 1: Write the failing test**

Дописать в `frontend/src/shared/workspace/tree.spec.ts`:

```ts
import {
  activatePanel,
  addPanel,
  movePanel,
  removePanel,
  resizeSplit,
  setCollapsed,
  splitLeaf,
} from "./tree"

describe("panels in a leaf", () => {
  it("adds a panel and makes it the active one", () => {
    const next = addPanel(sample(), "a", "p9") as SplitNode
    const leaf = next.children[0] as LeafNode
    expect(leaf.panels).toEqual(["p1", "p9"])
    expect(leaf.activePanel).toBe("p9")
  })

  it("ignores a leaf that is not there", () => {
    const tree = sample()
    expect(addPanel(tree, "nope", "p9")).toBe(tree)
  })

  it("removes a panel and leaves the others", () => {
    const next = removePanel(sample(), "p2") as SplitNode
    expect((next.children[1] as LeafNode).panels).toEqual(["p3"])
  })

  it("removes the leaf along with its last panel", () => {
    expect(removePanel(sample(), "p1")?.id).toBe("b")
  })

  it("activates a panel the leaf already holds", () => {
    const next = activatePanel(sample(), "p3") as SplitNode
    expect((next.children[1] as LeafNode).activePanel).toBe("p3")
  })
})

describe("collapsing a section", () => {
  it("marks the leaf and touches no size", () => {
    const next = setCollapsed(sample(), "a", true) as SplitNode
    expect((next.children[0] as LeafNode).collapsed).toBe(true)
    expect(next.sizes).toEqual([30, 70])
  })
})

describe("resizing", () => {
  it("moves what one side loses to the other", () => {
    const next = resizeSplit(sample(), "root", 0, 10, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(40)
    expect(next.sizes[1]).toBeCloseTo(60)
  })

  it("stops at the minimum instead of crossing it", () => {
    const next = resizeSplit(sample(), "root", 0, -100, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
    expect(next.sizes[1]).toBeCloseTo(90)
  })

  it("refuses to move a border that is already at the minimum", () => {
    const tight = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [10, 90])
    const next = resizeSplit(tight, "root", 0, -5, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
  })
})

describe("splitting a leaf", () => {
  it("puts the panel to the left in a row", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "left", "new") as SplitNode
    expect(next.direction).toBe("row")
    expect((next.children[0] as LeafNode).panels).toEqual(["p9"])
    expect((next.children[1] as LeafNode).panels).toEqual(["p1"])
    expect(next.sizes).toEqual([50, 50])
  })

  it("puts the panel below in a column", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "bottom", "new") as SplitNode
    expect(next.direction).toBe("column")
    expect((next.children[1] as LeafNode).panels).toEqual(["p9"])
  })

  it("adds the panel as a tab when the zone is the centre", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "center", "new") as LeafNode
    expect(next.kind).toBe("leaf")
    expect(next.panels).toEqual(["p1", "p9"])
  })
})

describe("moving a panel", () => {
  it("takes it out of one leaf and into another as a tab", () => {
    const next = movePanel(sample(), "p1", "b", "center", "new") as LeafNode
    expect(next.kind).toBe("leaf")
    expect(next.panels).toEqual(["p2", "p3", "p1"])
  })

  it("splits the target when the zone is an edge", () => {
    const next = movePanel(sample(), "p2", "a", "right", "new") as SplitNode
    expect(next.children.map((child) => (child as LeafNode).panels)).toEqual([
      ["p1"],
      ["p2"],
      ["p3"],
    ])
  })

  it("does nothing when the target leaf disappeared with the panel", () => {
    const tree = sample()
    expect(movePanel(tree, "p1", "a", "right", "new")).toBe(tree)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: FAIL — `addPanel is not exported`.

- [ ] **Step 3: Implement**

Дописать в `frontend/src/shared/workspace/tree.ts`:

```ts
import { makeLeaf } from "./model"
import type { DropZone } from "./model"

/** Normalise, and fall back to the tree we had when nothing would be left. */
function settle(root: LayoutNode, previous: LayoutNode): LayoutNode {
  return normalize(root) ?? previous
}

function withLeaf(
  root: LayoutNode,
  leafId: NodeId,
  change: (leaf: LeafNode) => LayoutNode | null
): LayoutNode {
  const path = pathOfNode(root, leafId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root
  const replaced = replaceAt(root, path, change(leaf))
  return replaced === null ? root : settle(replaced, root)
}

export function addPanel(root: LayoutNode, leafId: NodeId, panelId: PanelId): LayoutNode {
  return withLeaf(root, leafId, (leaf) =>
    leaf.panels.includes(panelId)
      ? { ...leaf, activePanel: panelId }
      : { ...leaf, panels: [...leaf.panels, panelId], activePanel: panelId }
  )
}

export function removePanel(root: LayoutNode, panelId: PanelId): LayoutNode | null {
  const path = pathOfPanel(root, panelId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root

  const panels = leaf.panels.filter((id) => id !== panelId)
  const next: LayoutNode | null =
    panels.length === 0
      ? null
      : {
          ...leaf,
          panels,
          activePanel: leaf.activePanel === panelId ? panels[0] : leaf.activePanel,
        }

  const replaced = replaceAt(root, path, next)
  return replaced === null ? null : normalize(replaced)
}

export function activatePanel(root: LayoutNode, panelId: PanelId): LayoutNode {
  const path = pathOfPanel(root, panelId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root
  return settle(replaceAt(root, path, { ...leaf, activePanel: panelId }) ?? root, root)
}

export function setCollapsed(root: LayoutNode, leafId: NodeId, collapsed: boolean): LayoutNode {
  return withLeaf(root, leafId, (leaf) => ({ ...leaf, collapsed }))
}

/**
 * Move the border between `children[index]` and `children[index + 1]`.
 *
 * Sizes are percentages and the limit is pixels, so the caller converts: the
 * component that owns the element knows how wide it is, and this function
 * knows nothing about the screen.
 */
export function resizeSplit(
  root: LayoutNode,
  splitId: NodeId,
  index: number,
  delta: number,
  minPercent: number
): LayoutNode {
  const path = pathOfNode(root, splitId)
  if (path === null) return root
  const split = nodeAt(root, path)
  if (split === null || split.kind !== "split") return root

  const before = split.sizes[index]
  const after = split.sizes[index + 1]
  if (before === undefined || after === undefined) return root

  const room = before + after
  const clamped = Math.min(Math.max(before + delta, minPercent), room - minPercent)
  if (!Number.isFinite(clamped) || clamped <= 0) return root

  const sizes = [...split.sizes]
  sizes[index] = clamped
  sizes[index + 1] = room - clamped

  const replaced = replaceAt(root, path, { ...split, sizes })
  // Normalised like every other operation. Resizing cannot on its own leave a
  // tree that needs repair, but an operation that skips the step is the crack
  // W4 exists to close: nothing downstream should have to know which ones do.
  return replaced === null ? root : settle(replaced, root)
}

const DIRECTION_OF: Record<Exclude<DropZone, "center">, "row" | "column"> = {
  left: "row",
  right: "row",
  top: "column",
  bottom: "column",
}

const FIRST: DropZone[] = ["left", "top"]

export function splitLeaf(
  root: LayoutNode,
  leafId: NodeId,
  panelId: PanelId,
  zone: DropZone,
  newLeafId: NodeId
): LayoutNode {
  if (zone === "center") return addPanel(root, leafId, panelId)

  return withLeaf(root, leafId, (leaf) => {
    const arrival = makeLeaf(newLeafId, [panelId])
    const children = FIRST.includes(zone) ? [arrival, leaf] : [leaf, arrival]
    return makeSplit(`split-${newLeafId}`, DIRECTION_OF[zone], children, [50, 50])
  })
}

/**
 * Take a panel out of wherever it is and put it into a target section.
 *
 * The removal happens first, and it may take the target section with it when
 * the panel was the only thing in it. That is not an error to work around: the
 * gesture had no destination, so nothing happens at all.
 */
export function movePanel(
  root: LayoutNode,
  panelId: PanelId,
  targetLeafId: NodeId,
  zone: DropZone,
  newLeafId: NodeId
): LayoutNode {
  const without = removePanel(root, panelId)
  if (without === null) return root
  if (pathOfNode(without, targetLeafId) === null) return root
  return splitLeaf(without, targetLeafId, panelId, zone, newLeafId)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bun run test:unit -- src/shared/workspace/tree.spec.ts`
Expected: PASS, 31 tests.

- [ ] **Step 5: Check the types and the style**

Run: `bun run type-check && bun run lint`
Expected: обе команды без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/workspace/tree.ts frontend/src/shared/workspace/tree.spec.ts
git commit -m "feat(workspace): add, remove, resize, split and move, all pure"
```

---

## Задача 4: зона сброса и выбор листа для новой панели

**Files:**
- Create: `frontend/src/shared/workspace/dropZone.ts`
- Create: `frontend/src/shared/workspace/dropZone.spec.ts`
- Create: `frontend/src/shared/workspace/placement.ts`
- Create: `frontend/src/shared/workspace/placement.spec.ts`

**Interfaces:**
- Consumes: `DropZone`, `LayoutNode`, `leavesOf`.
- Produces:
  - `dropZoneAt(rect: { left: number; top: number; width: number; height: number }, x: number, y: number): DropZone`
  - `leafForKind(root, kindOfPanel: (panelId: PanelId) => string | null, kind: string, focusedLeafId: NodeId | null): NodeId | null`

- [ ] **Step 1: Write the failing tests**

`frontend/src/shared/workspace/dropZone.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { dropZoneAt } from "./dropZone"

const rect = { left: 0, top: 0, width: 400, height: 200 }

describe("the zone a pointer is over", () => {
  it("is the centre in the middle", () => {
    expect(dropZoneAt(rect, 200, 100)).toBe("center")
  })

  it("is the left edge within a quarter of the width", () => {
    expect(dropZoneAt(rect, 20, 100)).toBe("left")
  })

  it("is the right edge past three quarters", () => {
    expect(dropZoneAt(rect, 380, 100)).toBe("right")
  })

  it("is the top edge within a quarter of the height", () => {
    expect(dropZoneAt(rect, 200, 10)).toBe("top")
  })

  it("is the bottom edge past three quarters", () => {
    expect(dropZoneAt(rect, 200, 190)).toBe("bottom")
  })

  it("prefers the horizontal edge in a corner, because the wider side wins", () => {
    expect(dropZoneAt(rect, 10, 10)).toBe("left")
  })

  it("prefers the vertical edge in the corner of a tall rectangle", () => {
    // The wide case on its own would pass against a rule that always picks
    // the horizontal edge, which is the rule this test exists to rule out.
    expect(dropZoneAt({ left: 0, top: 0, width: 200, height: 400 }, 10, 10)).toBe("top")
  })

  it("treats the quarter mark itself as the middle rather than the edge", () => {
    expect(dropZoneAt(rect, 100, 100)).toBe("center")
  })

  it("reads the rectangle's own origin rather than assuming zero", () => {
    expect(dropZoneAt({ left: 1000, top: 500, width: 400, height: 200 }, 1020, 600)).toBe("left")
  })

  it("answers the centre for a rectangle with no size", () => {
    expect(dropZoneAt({ left: 0, top: 0, width: 0, height: 0 }, 0, 0)).toBe("center")
  })
})
```

`frontend/src/shared/workspace/placement.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { makeLeaf, makeSplit } from "./model"
import { leafForKind } from "./placement"

const kinds: Record<string, string> = { p1: "catalog", p2: "rows", p3: "rows" }
const kindOf = (panelId: string) => kinds[panelId] ?? null

const tree = makeSplit(
  "root",
  "row",
  [makeLeaf("left", ["p1"]), makeLeaf("main", ["p2", "p3"])],
  [30, 70]
)

describe("where a new panel goes", () => {
  it("joins the section already holding a panel of its kind", () => {
    expect(leafForKind(tree, kindOf, "rows", null)).toBe("main")
  })

  it("falls back to the focused section when no section holds that kind", () => {
    expect(leafForKind(tree, kindOf, "editor", "left")).toBe("left")
  })

  it("falls back to the largest section when nothing has focus", () => {
    expect(leafForKind(tree, kindOf, "editor", null)).toBe("main")
  })

  it("ignores a focused section that is no longer there", () => {
    expect(leafForKind(tree, kindOf, "editor", "gone")).toBe("main")
  })

  it("answers null for a tree with no sections", () => {
    expect(leafForKind(makeSplit("root", "row", [], []), kindOf, "rows", null)).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bun run test:unit -- src/shared/workspace`
Expected: FAIL — `Failed to resolve import "./dropZone"` и `"./placement"`.

- [ ] **Step 3: Implement dropZone.ts**

```ts
import type { DropZone } from "./model"

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

/** How much of a side counts as its edge. */
const EDGE = 0.25

/**
 * Where a dragged panel would land if it were released here.
 *
 * The wider side wins in a corner: with the pointer in the top-left of a wide
 * section, splitting sideways is what the user is more likely to mean, and a
 * rule is better than whichever comparison happens to run first.
 */
export function dropZoneAt(rect: Rect, x: number, y: number): DropZone {
  if (rect.width <= 0 || rect.height <= 0) return "center"

  const fx = (x - rect.left) / rect.width
  const fy = (y - rect.top) / rect.height

  const horizontal: DropZone | null = fx < EDGE ? "left" : fx > 1 - EDGE ? "right" : null
  const vertical: DropZone | null = fy < EDGE ? "top" : fy > 1 - EDGE ? "bottom" : null

  if (horizontal !== null && vertical !== null) {
    return rect.width >= rect.height ? horizontal : vertical
  }
  return horizontal ?? vertical ?? "center"
}
```

- [ ] **Step 4: Implement placement.ts**

```ts
import type { LayoutNode, NodeId, PanelId } from "./model"
import { leavesOf, pathOfNode } from "./tree"

/**
 * Which section a newly opened panel belongs in.
 *
 * Read from the tree itself rather than from a record of where panels used to
 * live: a record can disagree with the tree, and the tree cannot disagree with
 * itself. See the spec, W11.
 */
export function leafForKind(
  root: LayoutNode,
  kindOfPanel: (panelId: PanelId) => string | null,
  kind: string,
  focusedLeafId: NodeId | null
): NodeId | null {
  const leaves = leavesOf(root)
  if (leaves.length === 0) return null

  const sameKind = leaves.find((leaf) => leaf.panels.some((id) => kindOfPanel(id) === kind))
  if (sameKind !== undefined) return sameKind.id

  if (focusedLeafId !== null && pathOfNode(root, focusedLeafId) !== null) return focusedLeafId

  let largest = leaves[0]
  let largestWeight = weightOf(root, largest.id)
  for (const leaf of leaves.slice(1)) {
    const weight = weightOf(root, leaf.id)
    if (weight > largestWeight) {
      largest = leaf
      largestWeight = weight
    }
  }
  return largest.id
}

/** The share of the whole area a section occupies: its sizes multiplied down. */
function weightOf(root: LayoutNode, leafId: NodeId): number {
  const path = pathOfNode(root, leafId)
  if (path === null) return 0

  let node: LayoutNode = root
  let weight = 1
  for (const index of path) {
    if (node.kind !== "split") break
    weight *= (node.sizes[index] ?? 0) / 100
    node = node.children[index]
  }
  return weight
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `bun run test:unit -- src/shared/workspace`
Expected: PASS, 49 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/workspace/dropZone.ts frontend/src/shared/workspace/dropZone.spec.ts frontend/src/shared/workspace/placement.ts frontend/src/shared/workspace/placement.spec.ts
git commit -m "feat(workspace): drop zones and where a new panel lands"
```

---

## Задача 5: сохранение раскладки

**Files:**
- Create: `frontend/src/shared/workspace/persist.ts`
- Create: `frontend/src/shared/workspace/persist.spec.ts`

**Interfaces:**
- Consumes: `LayoutNode` из `model.ts`.
- Produces:
  - `WORKSPACE_VERSION = 1`
  - `serializeWorkspace<P>(tree: LayoutNode, panels: P[]): string`
  - `parseWorkspace<P extends { id: string }>(raw: string | null, panelSchema: ZodType<P>): { tree: LayoutNode; panels: P[] } | null` — null означает «взять раскладку по умолчанию целиком». Ограничение на `P` стоит здесь, а не в вызывающем модуле: панель без `id` нельзя сопоставить с деревом, и об этом должен знать компилятор, а не комментарий.

- [ ] **Step 1: Write the failing test**

`frontend/src/shared/workspace/persist.spec.ts`:

```ts
import { describe, expect, it } from "vitest"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import { parseWorkspace, serializeWorkspace, WORKSPACE_VERSION } from "./persist"

const panelSchema = z.object({ id: z.string(), kind: z.literal("demo") })
type DemoPanel = z.infer<typeof panelSchema>

const panels: DemoPanel[] = [
  { id: "p1", kind: "demo" },
  { id: "p2", kind: "demo" },
]
const tree = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [40, 60])

describe("a stored workspace", () => {
  it("comes back the way it went in", () => {
    const restored = parseWorkspace(serializeWorkspace(tree, panels), panelSchema)
    expect(restored?.tree).toEqual(tree)
    expect(restored?.panels).toEqual(panels)
  })

  it("is refused when there is nothing stored", () => {
    expect(parseWorkspace(null, panelSchema)).toBeNull()
  })

  it("is refused when it is not json at all", () => {
    expect(parseWorkspace("{ not json", panelSchema)).toBeNull()
  })

  it("is refused when the version is not the one we write", () => {
    const raw = JSON.stringify({ version: WORKSPACE_VERSION + 1, tree, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a panel does not match the schema of the feature", () => {
    const raw = JSON.stringify({
      version: WORKSPACE_VERSION,
      tree,
      panels: [{ id: "p1", kind: "something-else" }],
    })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a section names a panel that was not stored", () => {
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree, panels: [panels[0]] })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when the active panel is not in the section", () => {
    const broken = makeSplit(
      "root",
      "row",
      [{ kind: "leaf", id: "a", panels: ["p1"], activePanel: "p2", collapsed: false }, makeLeaf("b", ["p2"])],
      [40, 60]
    )
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a split has a size for every child but one", () => {
    const broken = { ...tree, sizes: [100] }
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when the split with the wrong sizes is deep in the tree", () => {
    // The root here is sound, so this fails only if the check recurses.
    const deep = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit(
          "inner",
          "column",
          [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])],
          [34, 33, 33]
        ),
      ],
      [40, 60]
    )
    const raw = JSON.stringify({
      version: WORKSPACE_VERSION,
      tree: deep,
      panels: [...panels, { id: "p3", kind: "demo" }],
    })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/persist.spec.ts`
Expected: FAIL — `Failed to resolve import "./persist"`.

- [ ] **Step 3: Implement**

`frontend/src/shared/workspace/persist.ts`:

```ts
import { z } from "zod"
import type { ZodType } from "zod"

import type { LayoutNode, PanelId } from "./model"
import { leavesOf } from "./tree"

/**
 * A stored layout is untrusted input, like anything else that comes from
 * outside. It is parsed, cross-checked, and refused whole: half a restored
 * tree is worse than the default one. See the spec, W9.
 */

export const WORKSPACE_VERSION = 1

const leafSchema = z.object({
  kind: z.literal("leaf"),
  id: z.string(),
  panels: z.array(z.string()).min(1),
  activePanel: z.string(),
  collapsed: z.boolean(),
})

const nodeSchema: ZodType<LayoutNode> = z.lazy(() =>
  z.union([
    leafSchema,
    z.object({
      kind: z.literal("split"),
      id: z.string(),
      direction: z.union([z.literal("row"), z.literal("column")]),
      children: z.array(nodeSchema).min(2),
      sizes: z.array(z.number()).min(2),
    }),
  ])
)

export function serializeWorkspace<P>(tree: LayoutNode, panels: P[]): string {
  return JSON.stringify({ version: WORKSPACE_VERSION, tree, panels })
}

export function parseWorkspace<P extends { id: string }>(
  raw: string | null,
  panelSchema: ZodType<P>
): { tree: LayoutNode; panels: P[] } | null {
  if (raw === null) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }

  const envelope = z
    .object({
      version: z.literal(WORKSPACE_VERSION),
      tree: nodeSchema,
      panels: z.array(panelSchema),
    })
    .safeParse(parsed)
  if (!envelope.success) return null

  const { tree, panels } = envelope.data
  if (!sizesMatchChildren(tree)) return null

  const known = new Set<PanelId>(panels.map((panel) => panel.id))
  for (const leaf of leavesOf(tree)) {
    if (!leaf.panels.every((id) => known.has(id))) return null
    if (!leaf.panels.includes(leaf.activePanel)) return null
  }

  return { tree, panels }
}

function sizesMatchChildren(node: LayoutNode): boolean {
  if (node.kind === "leaf") return true
  if (node.sizes.length !== node.children.length) return false
  return node.children.every(sizesMatchChildren)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bun run test:unit -- src/shared/workspace/persist.spec.ts`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/workspace/persist.ts frontend/src/shared/workspace/persist.spec.ts
git commit -m "feat(workspace): a stored layout is parsed, cross-checked, or refused whole"
```

---

## Задача 6: контекст и композабл

**Files:**
- Create: `frontend/src/shared/workspace/context.ts`
- Create: `frontend/src/shared/workspace/useWorkspace.ts`
- Create: `frontend/src/shared/workspace/useWorkspace.spec.ts`

**Interfaces:**
- Consumes: всё из задач 1–5.
- Produces:
  - `workspaceKey: InjectionKey<WorkspaceContext>`
  - `interface WorkspaceContext` — то единственное, что видят компоненты движка
  - `useWorkspace<P extends { id: string }>(options): WorkspaceApi<P>`

Подпись целиком, на неё опираются задачи 7–8 и 11–13:

```ts
export interface PanelLook {
  title: string
  icon: string
}

export interface WorkspaceContext {
  tree: Ref<LayoutNode>
  focusedLeaf: Ref<NodeId | null>
  dragging: Ref<PanelId | null>
  lookOf: (panelId: PanelId) => PanelLook
  componentOf: (panelId: PanelId) => Component
  activate: (panelId: PanelId) => void
  close: (panelId: PanelId) => void
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  resize: (splitId: NodeId, index: number, delta: number, minPercent: number) => void
  startDrag: (panelId: PanelId) => void
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null) => void
}

export interface WorkspaceOptions<P extends { id: string }> {
  storageKey: string
  panelSchema: ZodType<P>
  defaults: () => { tree: LayoutNode; panels: P[] }
  kindOf: (panel: P) => string
  look: (panel: P) => PanelLook
  component: (panel: P) => Component
}

export interface WorkspaceApi<P extends { id: string }> {
  context: WorkspaceContext
  panels: Ref<P[]>
  open: (panel: P) => void
  reset: () => void
}
```

- [ ] **Step 1: Write the failing test**

`frontend/src/shared/workspace/useWorkspace.spec.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest"
import { defineComponent, h, nextTick } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import type { LeafNode, SplitNode } from "./model"
import { useWorkspace } from "./useWorkspace"

const panelSchema = z.object({ id: z.string(), kind: z.string() })
type DemoPanel = z.infer<typeof panelSchema>

const Stub = defineComponent({ setup: () => () => h("div") })

const defaults = () => ({
  tree: makeSplit("root", "row", [makeLeaf("left", ["p1"]), makeLeaf("main", ["p2"])], [30, 70]),
  panels: [
    { id: "p1", kind: "catalog" },
    { id: "p2", kind: "rows" },
  ] as DemoPanel[],
})

function build() {
  return useWorkspace<DemoPanel>({
    storageKey: "test-workspace",
    panelSchema,
    defaults,
    kindOf: (panel) => panel.kind,
    look: (panel) => ({ title: panel.id, icon: "square" }),
    component: () => Stub,
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe("a workspace", () => {
  it("starts from the defaults when nothing is stored", () => {
    expect(build().context.tree.value.id).toBe("root")
  })

  it("opens a new panel beside one of the same kind", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    const main = (workspace.context.tree.value as SplitNode).children[1] as LeafNode
    expect(main.panels).toEqual(["p2", "p3"])
    expect(main.activePanel).toBe("p3")
  })

  it("activates a panel that is already open instead of opening it twice", () => {
    const workspace = build()
    workspace.open({ id: "p1", kind: "catalog" })
    expect(workspace.panels.value).toHaveLength(2)
  })

  it("forgets a panel when it is closed", () => {
    const workspace = build()
    workspace.context.close("p1")
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p2"])
    expect(workspace.context.tree.value.id).toBe("main")
  })

  it("keeps the last panel rather than leaving an empty workspace", () => {
    const workspace = build()
    workspace.context.close("p1")
    workspace.context.close("p2")
    expect(workspace.panels.value).toHaveLength(1)
  })

  it("writes what it has to storage and reads it back", async () => {
    const first = build()
    first.open({ id: "p3", kind: "rows" })
    // The watcher persists on the next tick, so several changes in one tick
    // cost one write rather than one each. The test waits; the drag does not.
    await nextTick()
    const second = build()
    expect(second.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
  })

  it("falls back to the defaults when storage holds nonsense", () => {
    localStorage.setItem("test-workspace", "{ not json")
    expect(build().panels.value).toHaveLength(2)
  })

  it("returns to the defaults on reset, and stores them", async () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    await nextTick()
    workspace.reset()
    await nextTick()
    expect(workspace.panels.value).toHaveLength(2)
    // What is stored is the default layout now, not the one we left behind.
    expect(build().panels.value).toHaveLength(2)
  })

  it("moves a panel where a drag ends", () => {
    const workspace = build()
    workspace.context.startDrag("p1")
    workspace.context.endDrag("main", "center")
    expect(workspace.context.tree.value.kind).toBe("leaf")
    expect((workspace.context.tree.value as LeafNode).panels).toEqual(["p2", "p1"])
  })

  it("leaves the layout alone when a drag ends nowhere", () => {
    const workspace = build()
    const before = workspace.context.tree.value
    workspace.context.startDrag("p1")
    workspace.context.endDrag(null, null)
    expect(workspace.context.tree.value).toBe(before)
    expect(workspace.context.dragging.value).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/useWorkspace.spec.ts`
Expected: FAIL — `Failed to resolve import "./useWorkspace"`.

- [ ] **Step 3: Implement context.ts**

```ts
import type { Component, InjectionKey, Ref } from "vue"

import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"

/** What a panel shows of itself in a tab: nothing else about it is needed. */
export interface PanelLook {
  title: string
  icon: string
}

/**
 * The one thing the components of the engine are given.
 *
 * The type of a panel does not appear here: a panel is an id, and what it
 * looks like and which component renders it are answered by two functions the
 * feature supplied. That is what keeps the engine free of any knowledge about
 * the application. See the spec, W1.
 */
export interface WorkspaceContext {
  tree: Ref<LayoutNode>
  focusedLeaf: Ref<NodeId | null>
  dragging: Ref<PanelId | null>
  lookOf: (panelId: PanelId) => PanelLook
  componentOf: (panelId: PanelId) => Component
  activate: (panelId: PanelId) => void
  close: (panelId: PanelId) => void
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  resize: (splitId: NodeId, index: number, delta: number, minPercent: number) => void
  startDrag: (panelId: PanelId) => void
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null) => void
}

export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol("workspace")
```

- [ ] **Step 4: Implement useWorkspace.ts**

```ts
import { ref, watch } from "vue"
import type { Component, Ref } from "vue"
import type { ZodType } from "zod"

import { workspaceKey } from "./context"
import type { PanelLook, WorkspaceContext } from "./context"
import { nextId } from "./model"
import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"
import { parseWorkspace, serializeWorkspace } from "./persist"
import { leafForKind } from "./placement"
import { activatePanel, addPanel, movePanel, removePanel, resizeSplit, setCollapsed } from "./tree"

export { workspaceKey }
export type { PanelLook, WorkspaceContext }

export interface WorkspaceOptions<P extends { id: string }> {
  storageKey: string
  panelSchema: ZodType<P>
  defaults: () => { tree: LayoutNode; panels: P[] }
  kindOf: (panel: P) => string
  look: (panel: P) => PanelLook
  component: (panel: P) => Component
}

export interface WorkspaceApi<P extends { id: string }> {
  context: WorkspaceContext
  panels: Ref<P[]>
  open: (panel: P) => void
  reset: () => void
}

export function useWorkspace<P extends { id: string }>(
  options: WorkspaceOptions<P>
): WorkspaceApi<P> {
  const restored = parseWorkspace(localStorage.getItem(options.storageKey), options.panelSchema)
  const start = restored ?? options.defaults()

  // ref() rewrites a union into its own unwrapped shape, so the type is
  // restated: without this the discriminant on tree.value stops narrowing and
  // every kind check downstream fails to compile.
  const tree = ref<LayoutNode>(start.tree) as Ref<LayoutNode>
  const panels = ref<P[]>(start.panels) as Ref<P[]>
  const focusedLeaf = ref<NodeId | null>(null)
  const dragging = ref<PanelId | null>(null)

  const panelOf = (panelId: PanelId): P | undefined =>
    panels.value.find((panel) => panel.id === panelId)

  // Vue's default flush coalesces every change made in one tick into a single
  // write. flush: "sync" would put a synchronous localStorage write on every
  // frame of a border drag, which is a price the user pays so that a test can
  // skip an await.
  watch(
    [tree, panels],
    () => {
      localStorage.setItem(options.storageKey, serializeWorkspace(tree.value, panels.value))
    },
    { deep: true }
  )

  function open(panel: P) {
    if (panelOf(panel.id) !== undefined) {
      tree.value = activatePanel(tree.value, panel.id)
      return
    }
    const target = leafForKind(
      tree.value,
      (panelId) => {
        const found = panelOf(panelId)
        return found === undefined ? null : options.kindOf(found)
      },
      options.kindOf(panel),
      focusedLeaf.value
    )
    if (target === null) return
    panels.value = [...panels.value, panel]
    tree.value = addPanel(tree.value, target, panel.id)
  }

  function close(panelId: PanelId) {
    // The workspace never empties: a screen with no sections at all offers the
    // user nothing to act on, and no way back.
    if (panels.value.length <= 1) return
    const without = removePanel(tree.value, panelId)
    if (without === null) return
    tree.value = without
    panels.value = panels.value.filter((panel) => panel.id !== panelId)
  }

  const context: WorkspaceContext = {
    tree,
    focusedLeaf,
    dragging,
    lookOf: (panelId) => {
      const panel = panelOf(panelId)
      return panel === undefined ? { title: panelId, icon: "help" } : options.look(panel)
    },
    componentOf: (panelId) => {
      const panel = panelOf(panelId)
      if (panel === undefined) throw new Error(`No panel with id ${panelId}`)
      return options.component(panel)
    },
    activate: (panelId) => {
      tree.value = activatePanel(tree.value, panelId)
    },
    close,
    focus: (leafId) => {
      focusedLeaf.value = leafId
    },
    toggleCollapse: (leafId) => {
      // A workspace of one section has nothing to collapse against, and
      // WorkspaceNode does not offer the handle there either.
      if (tree.value.kind === "leaf") return
      tree.value = setCollapsed(tree.value, leafId, !collapsedOf(tree.value, leafId))
    },
    resize: (splitId, index, delta, minPercent) => {
      tree.value = resizeSplit(tree.value, splitId, index, delta, minPercent)
    },
    startDrag: (panelId) => {
      dragging.value = panelId
    },
    endDrag: (targetLeafId, zone) => {
      const panelId = dragging.value
      dragging.value = null
      if (panelId === null || targetLeafId === null || zone === null) return
      tree.value = movePanel(tree.value, panelId, targetLeafId, zone, nextId("leaf"))
    },
  }

  function reset() {
    // Assign and let the watcher persist, rather than clearing the key and
    // racing the write that the assignment itself schedules.
    const fresh = options.defaults()
    tree.value = fresh.tree
    panels.value = fresh.panels
    focusedLeaf.value = null
  }

  return { context, panels, open, reset }
}

function collapsedOf(root: LayoutNode, leafId: NodeId): boolean {
  if (root.kind === "leaf") return root.id === leafId && root.collapsed
  return root.children.some((child) => collapsedOf(child, leafId))
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bun run test:unit -- src/shared/workspace/useWorkspace.spec.ts`
Expected: PASS, 10 tests.

- [ ] **Step 6: Check types and style**

Run: `bun run type-check && bun run lint`
Expected: чисто.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/shared/workspace/context.ts frontend/src/shared/workspace/useWorkspace.ts frontend/src/shared/workspace/useWorkspace.spec.ts
git commit -m "feat(workspace): the composable, and the one context the components see"
```

---

## Задача 7: компоненты движка

**Files:**
- Create: `frontend/src/shared/workspace/WorkspaceRoot.vue`
- Create: `frontend/src/shared/workspace/WorkspaceNode.vue`
- Create: `frontend/src/shared/workspace/WorkspaceLeaf.vue`
- Create: `frontend/src/shared/workspace/WorkspaceSeparator.vue`
- Create: `frontend/src/shared/workspace/index.ts`
- Create: `frontend/src/shared/workspace/WorkspaceLeaf.spec.ts`

**Interfaces:**
- Consumes: `workspaceKey`, `WorkspaceContext` из задачи 6; `dropZoneAt` из задачи 4; `COLLAPSED_PX`, `MIN_PANEL_PX` из задачи 1.
- Produces: `index.ts` экспортирует `WorkspaceRoot`, `useWorkspace`, типы `LayoutNode`, `PanelLook`, `WorkspaceContext`, конструкторы `makeLeaf`, `makeSplit`, `nextId`.
- `WorkspaceRoot` props: `{ context: WorkspaceContext }` — он же выполняет `provide(workspaceKey, context)`.
- `WorkspaceNode` props: `{ node: LayoutNode }`, рекурсивен сам в себя.
- `WorkspaceLeaf` props: `{ leaf: LeafNode; collapsible: boolean }`.
- `WorkspaceSeparator` props: `{ direction: Direction }`, emit `move: [deltaPx: number]`.

Названия `data-testid`, на которые опираются задачи 8 и 14:
`workspace`, `workspace-leaf-{leafId}`, `workspace-tab-{panelId}`, `workspace-close-{panelId}`, `workspace-collapse-{leafId}`, `workspace-separator`, `workspace-dropzone`.

- [ ] **Step 1: Write the failing test**

`frontend/src/shared/workspace/WorkspaceLeaf.spec.ts`:

```ts
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import { defineComponent, h, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { makeLeaf } from "./model"
import WorkspaceLeaf from "./WorkspaceLeaf.vue"

const Stub = defineComponent({ setup: () => () => h("div", { class: "stub" }, "panel body") })

function contextFor(overrides: Partial<WorkspaceContext> = {}): WorkspaceContext {
  return {
    tree: ref(makeLeaf("a", ["p1", "p2"])),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    activate: () => undefined,
    close: () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    resize: () => undefined,
    startDrag: () => undefined,
    endDrag: () => undefined,
    ...overrides,
  }
}

function mountLeaf(context: WorkspaceContext, collapsible = true) {
  return mount(WorkspaceLeaf, {
    props: { leaf: makeLeaf("a", ["p1", "p2"]), collapsible },
    global: { provide: { [workspaceKey as symbol]: context } },
  })
}

describe("a section", () => {
  it("shows a tab per panel, titled by the feature", () => {
    const wrapper = mountLeaf(contextFor())
    expect(wrapper.get('[data-testid="workspace-tab-p1"]').text()).toContain("title p1")
    expect(wrapper.get('[data-testid="workspace-tab-p2"]').text()).toContain("title p2")
  })

  it("renders only the active panel", () => {
    expect(mountLeaf(contextFor()).findAll(".stub")).toHaveLength(1)
  })

  it("activates the panel whose tab is clicked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ activate: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-tab-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it("closes the panel whose cross is clicked", async () => {
    const seen: string[] = []
    const wrapper = mountLeaf(contextFor({ close: (id) => seen.push(id) }))
    await wrapper.get('[data-testid="workspace-close-p2"]').trigger("click")
    expect(seen).toEqual(["p2"])
  })

  it("offers no collapse handle when it is the only section", () => {
    const wrapper = mountLeaf(contextFor(), false)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(false)
  })

  it("hides the body of a collapsed section but keeps the strip", () => {
    const wrapper = mount(WorkspaceLeaf, {
      props: { leaf: { ...makeLeaf("a", ["p1"]), collapsed: true }, collapsible: true },
      global: { provide: { [workspaceKey as symbol]: contextFor() } },
    })
    expect(wrapper.findAll(".stub")).toHaveLength(0)
    expect(wrapper.find('[data-testid="workspace-collapse-a"]').exists()).toBe(true)
  })

  it("shows a drop overlay only while something is being dragged", async () => {
    const dragging = ref<string | null>(null)
    const wrapper = mountLeaf(contextFor({ dragging }))
    expect(wrapper.find('[data-testid="workspace-dropzone"]').exists()).toBe(false)
    dragging.value = "p1"
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="workspace-dropzone"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/shared/workspace/WorkspaceLeaf.spec.ts`
Expected: FAIL — `Failed to resolve import "./WorkspaceLeaf.vue"`.

- [ ] **Step 3: Write WorkspaceSeparator.vue**

```vue
<script setup lang="ts">
import { ref } from "vue"

import type { Direction } from "./model"

const props = defineProps<{ direction: Direction }>()
const emit = defineEmits<{ move: [deltaPx: number]; toggle: [] }>()

const dragging = ref(false)
let origin = 0
let moved = 0

function onPointerDown(event: PointerEvent) {
  ;(event.target as HTMLElement).setPointerCapture(event.pointerId)
  dragging.value = true
  moved = 0
  origin = props.direction === "row" ? event.clientX : event.clientY
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return
  const now = props.direction === "row" ? event.clientX : event.clientY
  const delta = now - origin
  origin = now
  moved += Math.abs(delta)
  emit("move", delta)
}

function onPointerUp(event: PointerEvent) {
  if (!dragging.value) return
  ;(event.target as HTMLElement).releasePointerCapture(event.pointerId)
  dragging.value = false
  // A border that was pressed rather than dragged is the handle that brings a
  // collapsed section back, which is why a collapsed section keeps its border.
  if (moved < 3) emit("toggle")
}
</script>

<template>
  <div
    class="workspace-separator"
    :class="direction === 'row' ? 'workspace-separator--row' : 'workspace-separator--column'"
    data-testid="workspace-separator"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  />
</template>

<style scoped>
.workspace-separator {
  flex: 0 0 5px;
  background: rgba(0, 0, 0, 0.12);
}
.workspace-separator--row {
  cursor: col-resize;
}
.workspace-separator--column {
  cursor: row-resize;
}
.workspace-separator:hover {
  background: rgba(0, 0, 0, 0.28);
}
</style>
```

- [ ] **Step 4: Write WorkspaceLeaf.vue**

```vue
<script setup lang="ts">
import { computed, inject, ref } from "vue"

import { workspaceKey } from "./context"
import { dropZoneAt } from "./dropZone"
import type { DropZone, LeafNode } from "./model"

const props = defineProps<{ leaf: LeafNode; collapsible: boolean }>()

const workspace = inject(workspaceKey)
if (workspace === undefined) throw new Error("WorkspaceLeaf used outside a WorkspaceRoot")

const element = ref<HTMLElement | null>(null)
const zone = ref<DropZone | null>(null)

const active = computed(() => props.leaf.activePanel)

function onPointerMove(event: PointerEvent) {
  if (workspace.dragging.value === null || element.value === null) return
  zone.value = dropZoneAt(element.value.getBoundingClientRect(), event.clientX, event.clientY)
}

function onPointerUp() {
  if (workspace.dragging.value === null) return
  workspace.endDrag(props.leaf.id, zone.value)
  zone.value = null
}

function onTabPointerDown(panelId: string) {
  workspace.focus(props.leaf.id)
  workspace.activate(panelId)
  workspace.startDrag(panelId)
}

const overlayStyle = computed(() => {
  const box: Record<DropZone, Record<string, string>> = {
    left: { left: "0", top: "0", width: "50%", height: "100%" },
    right: { left: "50%", top: "0", width: "50%", height: "100%" },
    top: { left: "0", top: "0", width: "100%", height: "50%" },
    bottom: { left: "0", top: "50%", width: "100%", height: "50%" },
    center: { left: "0", top: "0", width: "100%", height: "100%" },
  }
  return zone.value === null ? { display: "none" } : { position: "absolute", ...box[zone.value] }
})
</script>

<template>
  <div
    ref="element"
    class="workspace-leaf"
    :data-testid="`workspace-leaf-${leaf.id}`"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  >
    <div class="workspace-leaf__strip">
      <button
        v-for="panelId in leaf.panels"
        :key="panelId"
        type="button"
        class="workspace-leaf__tab"
        :class="{ 'workspace-leaf__tab--active': panelId === active }"
        :data-testid="`workspace-tab-${panelId}`"
        @pointerdown="onTabPointerDown(panelId)"
        @click="workspace.activate(panelId)"
      >
        <q-icon
          :name="workspace.lookOf(panelId).icon"
          size="16px"
        />
        <span class="workspace-leaf__title">{{ workspace.lookOf(panelId).title }}</span>
        <span
          class="workspace-leaf__close"
          :data-testid="`workspace-close-${panelId}`"
          @click.stop="workspace.close(panelId)"
        >
          <q-icon
            name="close"
            size="14px"
          />
        </span>
      </button>

      <span class="workspace-leaf__spacer" />

      <button
        v-if="collapsible"
        type="button"
        class="workspace-leaf__collapse"
        :data-testid="`workspace-collapse-${leaf.id}`"
        @click="workspace.toggleCollapse(leaf.id)"
      >
        <q-icon
          :name="leaf.collapsed ? 'chevron_right' : 'chevron_left'"
          size="16px"
        />
      </button>
    </div>

    <div
      v-if="!leaf.collapsed"
      class="workspace-leaf__body"
    >
      <component :is="workspace.componentOf(active)" />
    </div>

    <div
      v-if="workspace.dragging.value !== null"
      class="workspace-leaf__overlay"
      data-testid="workspace-dropzone"
    >
      <div
        class="workspace-leaf__zone"
        :style="overlayStyle"
      />
    </div>
  </div>
</template>

<style scoped>
.workspace-leaf {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}
.workspace-leaf__strip {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  overflow: hidden;
}
.workspace-leaf__tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: 4px 4px 0 0;
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.workspace-leaf__tab--active {
  background: rgba(0, 0, 0, 0.06);
  font-weight: 500;
}
.workspace-leaf__title {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
.workspace-leaf__spacer {
  flex: 1;
}
.workspace-leaf__collapse {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 2px;
}
.workspace-leaf__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.workspace-leaf__overlay {
  position: absolute;
  inset: 0;
}
.workspace-leaf__zone {
  background: rgba(25, 118, 210, 0.18);
  border: 2px solid rgba(25, 118, 210, 0.6);
  border-radius: 4px;
}
</style>
```

- [ ] **Step 5: Write WorkspaceNode.vue**

```vue
<script setup lang="ts">
import { computed, ref } from "vue"

import { COLLAPSED_PX, MIN_PANEL_PX } from "./model"
import type { LayoutNode } from "./model"
import { inject } from "vue"
import { workspaceKey } from "./context"
import WorkspaceLeaf from "./WorkspaceLeaf.vue"
import WorkspaceSeparator from "./WorkspaceSeparator.vue"

const props = defineProps<{ node: LayoutNode }>()

const workspace = inject(workspaceKey)
if (workspace === undefined) throw new Error("WorkspaceNode used outside a WorkspaceRoot")

const element = ref<HTMLElement | null>(null)

/**
 * A collapsed child takes a fixed strip and the rest divide what is left in
 * proportion to their stored sizes. That is why collapsing never touches
 * `sizes`: the size a section had is still written where it belongs.
 */
function styleFor(child: LayoutNode, index: number) {
  if (child.kind === "leaf" && child.collapsed) {
    return { flex: `0 0 ${String(COLLAPSED_PX)}px` }
  }
  const size = props.node.kind === "split" ? (props.node.sizes[index] ?? 0) : 100
  return { flex: `${String(size)} 1 0%` }
}

const lengthPx = computed(() => {
  if (element.value === null) return 0
  const box = element.value.getBoundingClientRect()
  return props.node.kind === "split" && props.node.direction === "row" ? box.width : box.height
})

function onMove(index: number, deltaPx: number) {
  if (props.node.kind !== "split") return
  const total = lengthPx.value
  if (total <= 0) return
  workspace.resize(
    props.node.id,
    index,
    (deltaPx / total) * 100,
    (MIN_PANEL_PX / total) * 100
  )
}

/** Pressing rather than dragging a border brings back whichever side is collapsed. */
function onToggle(index: number) {
  if (props.node.kind !== "split") return
  for (const child of [props.node.children[index], props.node.children[index + 1]]) {
    if (child.kind === "leaf" && child.collapsed) {
      workspace.toggleCollapse(child.id)
      return
    }
  }
}
</script>

<template>
  <WorkspaceLeaf
    v-if="node.kind === 'leaf'"
    :leaf="node"
    :collapsible="false"
  />
  <div
    v-else
    ref="element"
    class="workspace-node"
    :style="{ flexDirection: node.direction }"
  >
    <template
      v-for="(child, index) in node.children"
      :key="child.id"
    >
      <WorkspaceSeparator
        v-if="index > 0"
        :direction="node.direction"
        @move="onMove(index - 1, $event)"
        @toggle="onToggle(index - 1)"
      />
      <WorkspaceLeaf
        v-if="child.kind === 'leaf'"
        :leaf="child"
        :collapsible="true"
        :style="styleFor(child, index)"
      />
      <WorkspaceNode
        v-else
        :node="child"
        :style="styleFor(child, index)"
      />
    </template>
  </div>
</template>

<style scoped>
.workspace-node {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
</style>
```

- [ ] **Step 6: Write WorkspaceRoot.vue and index.ts**

`WorkspaceRoot.vue`:

```vue
<script setup lang="ts">
import { provide } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import WorkspaceNode from "./WorkspaceNode.vue"

const props = defineProps<{ context: WorkspaceContext }>()

provide(workspaceKey, props.context)

/** A drag released outside every section is a drag that came to nothing. */
function onPointerUp() {
  if (props.context.dragging.value !== null) props.context.endDrag(null, null)
}
</script>

<template>
  <div
    class="workspace"
    data-testid="workspace"
    @pointerup="onPointerUp"
  >
    <WorkspaceNode :node="context.tree.value" />
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
```

`index.ts`:

```ts
/**
 * A workspace of resizable sections holding panels.
 *
 * The engine knows nothing about what a panel shows: a feature supplies the
 * panel type, a component per panel and a look per panel, and gets a layout
 * that can be resized, collapsed, tabbed and rearranged.
 */
export { default as WorkspaceRoot } from "./WorkspaceRoot.vue"
export { useWorkspace, workspaceKey } from "./useWorkspace"
export type { PanelLook, WorkspaceApi, WorkspaceContext, WorkspaceOptions } from "./useWorkspace"
export { COLLAPSED_PX, makeLeaf, makeSplit, MIN_PANEL_PX, nextId } from "./model"
export type { DropZone, LayoutNode, LeafNode, NodeId, PanelId, SplitNode } from "./model"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `bun run test:unit -- src/shared/workspace`
Expected: PASS, 51 tests.

- [ ] **Step 8: Check types and style**

Run: `bun run type-check && bun run lint`
Expected: чисто. `q-icon` разрешён вне кита — у него нет выбора внешнего вида, он в списке необёрнутых в спеке кита.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/shared/workspace
git commit -m "feat(workspace): the components, driven by one injected context"
```

---

## Задача 8: показ движка на dev-маршруте и сценарий Playwright

**Files:**
- Create: `frontend/src/features/dev/WorkspaceDemoPage.vue`
- Modify: `frontend/src/router/index.ts`
- Create: `frontend/tests/workspace.spec.ts`

**Interfaces:**
- Consumes: `WorkspaceRoot`, `useWorkspace`, `makeLeaf`, `makeSplit` из `@/shared/workspace`.
- Produces: маршрут `/workspace-demo`, только под `import.meta.env.DEV`, без авторизации — как `/ui-kit`.

- [ ] **Step 1: Write the failing Playwright scenario**

`frontend/tests/workspace.spec.ts`:

```ts
import { expect, test } from "@playwright/test"

/**
 * The engine is exercised on its own route with placeholder panels: nothing
 * here touches a connector, so a failure is a failure of the layout and not of
 * the data behind it.
 */

test("resizes, collapses and remembers the layout", async ({ page }) => {
  await page.goto("/workspace-demo")

  const alpha = page.getByTestId("workspace-leaf-left")
  const before = (await alpha.boundingBox())?.width ?? 0
  expect(before).toBeGreaterThan(0)

  const separator = page.getByTestId("workspace-separator").first()
  const box = await separator.boundingBox()
  if (box === null) throw new Error("the separator has no box")
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 10 })
  await page.mouse.up()

  const after = (await alpha.boundingBox())?.width ?? 0
  expect(after).toBeGreaterThan(before + 50)

  await page.reload()
  const restored = (await alpha.boundingBox())?.width ?? 0
  expect(Math.abs(restored - after)).toBeLessThan(6)

  await page.getByTestId("workspace-collapse-left").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeLessThan(40)

  await page.getByTestId("reset-workspace").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeGreaterThan(50)
})

test("opens a panel as a tab and closes it again", async ({ page }) => {
  await page.goto("/workspace-demo")
  await page.getByTestId("reset-workspace").click()

  await page.getByTestId("open-demo-panel").click()
  const tab = page.getByTestId("workspace-tab-demo-1")
  await expect(tab).toBeVisible()

  await page.getByTestId("workspace-close-demo-1").click()
  await expect(tab).toHaveCount(0)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `bunx playwright test tests/workspace.spec.ts`
Expected: FAIL — страница `/workspace-demo` не найдена, `workspace-leaf-left` отсутствует.

- [ ] **Step 3: Write WorkspaceDemoPage.vue**

```vue
<script setup lang="ts">
import { defineComponent, h } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit, useWorkspace, WorkspaceRoot } from "@/shared/workspace"
import { AppButton } from "@/shared/ui"

/**
 * The engine on its own, with panels that show nothing but their own name.
 * A development route, like /ui-kit: it renders the real components, so it
 * breaks when one of them does.
 */

const panelSchema = z.object({ id: z.string(), kind: z.string(), title: z.string() })
type DemoPanel = z.infer<typeof panelSchema>

const Placeholder = (title: string) =>
  defineComponent({
    setup: () => () => h("div", { style: "padding: 12px; font-size: 13px;" }, title),
  })

const workspace = useWorkspace<DemoPanel>({
  storageKey: "dataplayer-workspace-demo",
  panelSchema,
  defaults: () => ({
    tree: makeSplit(
      "root",
      "row",
      [makeLeaf("left", ["alpha"]), makeLeaf("main", ["beta", "gamma"])],
      [30, 70]
    ),
    panels: [
      { id: "alpha", kind: "alpha", title: "Alpha" },
      { id: "beta", kind: "beta", title: "Beta" },
      { id: "gamma", kind: "beta", title: "Gamma" },
    ],
  }),
  kindOf: (panel) => panel.kind,
  look: (panel) => ({ title: panel.title, icon: "widgets" }),
  component: (panel) => Placeholder(panel.title),
})

let opened = 0

function openOne() {
  opened += 1
  const id = `demo-${String(opened)}`
  workspace.open({ id, kind: "demo", title: `Demo ${String(opened)}` })
}
</script>

<template>
  <div class="demo">
    <div class="demo__bar">
      <AppButton
        size="sm"
        label="Open a panel"
        data-testid="open-demo-panel"
        @click="openOne"
      />
      <AppButton
        size="sm"
        variant="quiet"
        label="Reset layout"
        data-testid="reset-workspace"
        @click="workspace.reset()"
      />
    </div>
    <div class="demo__area">
      <WorkspaceRoot :context="workspace.context" />
    </div>
  </div>
</template>

<style scoped>
.demo {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.demo__bar {
  display: flex;
  gap: 8px;
  padding: 8px;
}
.demo__area {
  flex: 1;
  min-height: 0;
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
</style>
```

- [ ] **Step 4: Register the route**

В `frontend/src/router/index.ts`, внутри `devRoutes`, после записи `ui-kit`:

```ts
      {
        path: "/workspace-demo",
        name: "workspace-demo",
        // The engine renders no server data, so it opens without a backend.
        component: () => import("@/features/dev/WorkspaceDemoPage.vue"),
      },
```

- [ ] **Step 5: Run the scenario to verify it passes**

Run: `bunx playwright test tests/workspace.spec.ts`
Expected: PASS, 2 сценария. Если браузер не установлен: `bunx playwright install chromium`.

- [ ] **Step 6: Full frontend check**

Run: `bun run test:unit && bun run lint && bun run type-check`
Expected: всё чисто.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/dev/WorkspaceDemoPage.vue frontend/src/router/index.ts frontend/tests/workspace.spec.ts
git commit -m "feat(workspace): show the engine at /workspace-demo and prove it in a browser"
```

---

# Этап B — рабочая область

## Задача 9: полноэкранная оболочка и дерево в ките

**Files:**
- Modify: `frontend/src/shared/ui/AppLayout.vue`
- Create: `frontend/src/shared/ui/AppTree.vue`
- Modify: `frontend/src/shared/ui/index.ts`
- Modify: `frontend/src/features/dev/UiKitPage.vue`
- Modify: `frontend/eslint.config.js`

**Interfaces:**
- Produces:
  - `AppLayout` получает необязательный проп `fill?: boolean` — без внутренних отступов и на всю высоту.
  - `AppTree` props: `{ nodes: unknown[]; nodeKey: string; expanded: string[]; selected: string | null }`, `v-model:expanded`, `v-model:selected`, emit `lazyLoad`, слот `default-header`. Проброс остальных атрибутов включён.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/dev/kit.spec.ts` уже требует, чтобы каждый файл в `shared/ui/*.vue` был показан в `UiKitPage.vue` и экспортирован из бочки. Тест начнёт падать сам, как только появится `AppTree.vue`.

Создать пустой каркас `frontend/src/shared/ui/AppTree.vue` c одной строкой `<template><div /></template>` и запустить:

Run: `bun run test:unit -- src/features/dev/kit.spec.ts`
Expected: FAIL — `demonstrates AppTree` и `exports AppTree`.

- [ ] **Step 2: Implement AppTree.vue**

```vue
<script setup lang="ts">
/**
 * The catalog tree.
 *
 * Quasar's tree stays underneath, but a screen asks the kit for it: that keeps
 * the lint rule able to forbid <q-tree> outside the kit, and leaves one place
 * to change if the tree is ever replaced.
 */
defineProps<{
  nodes: readonly unknown[]
  nodeKey: string
  expanded: string[]
  selected: string | null
}>()

defineEmits<{
  "update:expanded": [value: string[]]
  "update:selected": [value: string | null]
  lazyLoad: [payload: unknown]
}>()
</script>

<template>
  <q-tree
    :nodes="nodes"
    :node-key="nodeKey"
    :expanded="expanded"
    :selected="selected"
    @update:expanded="$emit('update:expanded', $event)"
    @update:selected="$emit('update:selected', $event)"
    @lazy-load="$emit('lazyLoad', $event)"
  >
    <template #default-header="scope">
      <slot
        name="default-header"
        v-bind="scope"
      />
    </template>
  </q-tree>
</template>
```

- [ ] **Step 3: Add `fill` to AppLayout.vue**

Заменить блок `<script setup lang="ts">` начало на добавление пропа и изменить разметку страницы:

```ts
defineProps<{ fill?: boolean }>()
```

и в шаблоне:

```vue
    <q-page-container>
      <q-page :padding="!fill">
        <slot />
      </q-page>
    </q-page-container>
```

плюс стиль, чтобы страница занимала высоту:

```vue
<style scoped>
:deep(.q-page) {
  display: flex;
  flex-direction: column;
}
</style>
```

- [ ] **Step 4: Export it and demonstrate it**

В `frontend/src/shared/ui/index.ts`, в алфавитном порядке между `AppToggle` и `AppTooltip`:

```ts
export { default as AppTree } from "./AppTree.vue"
```

В `frontend/src/features/dev/UiKitPage.vue` добавить раздел перед секцией «A dialog», в `<script setup>`:

```ts
const treeNodes = [
  { id: "public", label: "public", children: [{ id: "orders", label: "orders" }] },
]
const treeExpanded = ref<string[]>(["public"])
const treeSelected = ref<string | null>(null)
```

и в шаблоне:

```vue
    <AppCard
      title="Tree"
      subtitle="the catalog tree, wrapped so screens ask the kit for it"
    >
      <AppSection>
        <AppTree
          v-model:expanded="treeExpanded"
          v-model:selected="treeSelected"
          :nodes="treeNodes"
          node-key="id"
        >
          <template #default-header="{ node }">
            <span>{{ node.label }}</span>
          </template>
        </AppTree>
      </AppSection>
    </AppCard>
```

Импорты `AppCard`, `AppSection`, `AppTree` добавить в существующий блок импорта из `@/shared/ui`.

- [ ] **Step 5: Forbid q-tree outside the kit**

В `frontend/eslint.config.js`, в массив пар правила `vue/no-restricted-html-elements`, после `["q-spinner", "AppSpinner"]`:

```js
          ["q-tree", "AppTree"],
```

- [ ] **Step 6: Run the checks**

Run: `bun run test:unit -- src/features/dev/kit.spec.ts && bun run type-check`
Expected: чисто.

Run: `bun run lint`
Expected: ровно одна ошибка — `q-tree` в `src/features/catalog/CatalogDialog.vue`, файле, который удаляется задачей 12. Это и есть доказательство, что новое правило работает: убедиться, что ошибка названа, и идти дальше. Если ошибок больше одной или нет ни одной — правило написано не так, разбираться здесь, а не позже.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/shared/ui/AppTree.vue frontend/src/shared/ui/index.ts frontend/src/shared/ui/AppLayout.vue frontend/src/features/dev/UiKitPage.vue frontend/eslint.config.js
git commit -m "feat(ui): the catalog tree joins the kit, and the layout can fill the screen"
```

---

## Задача 10: логика дерева каталога отдельно от диалога

**Files:**
- Create: `frontend/src/features/catalog/useCatalogTree.ts`
- Create: `frontend/src/features/catalog/useCatalogTree.spec.ts`

**Interfaces:**
- Consumes: `useCatalogLoader` из `features/catalog/api.ts`, `toTreeNodes`, `TreeNode` из `treeNodes.ts`, `messageOf` из `@/shared/api/errors`.
- Produces:

```ts
export interface CatalogTree {
  roots: Ref<TreeNode[]>
  expanded: Ref<string[]>
  selectedId: Ref<string | null>
  selected: ComputedRef<TreeNode | null>
  loading: Ref<boolean>
  error: Ref<string>
  load: () => Promise<void>
  reload: (nodeId: string | null) => Promise<void>
  onLazyLoad: (payload: { node: TreeNode; done: (children: TreeNode[]) => void; fail: () => void }) => Promise<void>
}

export function useCatalogTree(connectorId: Ref<string>): CatalogTree
```

- [ ] **Step 1: Write the failing test**

`frontend/src/features/catalog/useCatalogTree.spec.ts`:

```ts
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, h, ref } from "vue"

import { ConnectorsService } from "@/client"
import { useCatalogTree } from "./useCatalogTree"
import type { CatalogTree } from "./useCatalogTree"

function withTree(run: (tree: CatalogTree) => Promise<void>) {
  return new Promise<void>((resolve, reject) => {
    const Host = defineComponent({
      setup() {
        const tree = useCatalogTree(ref("c1"))
        run(tree).then(resolve).catch(reject)
        return () => h("div")
      },
    })
    mount(Host, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
  })
}

const node = (id: string, name: string) => ({
  id,
  name,
  kind: "table" as const,
  has_children: true,
  row_count_estimate: 10,
})

describe("the catalog tree", () => {
  it("loads the roots", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [node("public.orders", "orders")],
    } as never)

    await withTree(async (tree) => {
      await tree.load()
      expect(tree.roots.value.map((root) => root.label)).toEqual(["orders"])
      expect(tree.error.value).toBe("")
    })
  })

  it("keeps the reason a branch could not be read", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockRejectedValue(new Error("no route to host"))

    await withTree(async (tree) => {
      await tree.load()
      expect(tree.roots.value).toEqual([])
      expect(tree.error.value).not.toBe("")
    })
  })

  it("drops a selection the reload no longer holds", async () => {
    vi.spyOn(ConnectorsService, "readCatalog")
      .mockResolvedValueOnce({ data: [node("a", "a"), node("b", "b")] } as never)
      .mockResolvedValueOnce({ data: [node("a", "a")] } as never)

    await withTree(async (tree) => {
      await tree.load()
      tree.selectedId.value = "b"
      await tree.reload(null)
      expect(tree.selectedId.value).toBeNull()
    })
  })

  it("resolves a selection to the node it names", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [node("a", "orders")],
    } as never)

    await withTree(async (tree) => {
      await tree.load()
      tree.selectedId.value = "a"
      expect(tree.selected.value?.label).toBe("orders")
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/features/catalog/useCatalogTree.spec.ts`
Expected: FAIL — `Failed to resolve import "./useCatalogTree"`.

- [ ] **Step 3: Implement**

Перенести логику из `CatalogDialog.vue` (строки со `roots`, `expanded`, `nodesById`, `selectedId`, `selected`, `remember`, `reload`, `onLazyLoad`) в `frontend/src/features/catalog/useCatalogTree.ts`, заменив `props.connector.id` на `connectorId.value` и обращение к `props.modelValue` на явный вызов `load()`:

```ts
import { computed, ref } from "vue"
import type { ComputedRef, Ref } from "vue"

import { useCatalogLoader } from "@/features/catalog/api"
import { toTreeNodes } from "@/features/catalog/treeNodes"
import type { TreeNode } from "@/features/catalog/treeNodes"
import { messageOf } from "@/shared/api/errors"

export interface CatalogTree {
  roots: Ref<TreeNode[]>
  expanded: Ref<string[]>
  selectedId: Ref<string | null>
  selected: ComputedRef<TreeNode | null>
  loading: Ref<boolean>
  error: Ref<string>
  load: () => Promise<void>
  reload: (nodeId: string | null) => Promise<void>
  onLazyLoad: (payload: {
    node: TreeNode
    done: (children: TreeNode[]) => void
    fail: () => void
  }) => Promise<void>
}

/**
 * Walking a catalog one level at a time.
 *
 * Lives apart from any component: it was never logic of a dialog, and the
 * workspace panel needs the same behaviour without one.
 */
export function useCatalogTree(connectorId: Ref<string>): CatalogTree {
  const loadChildren = useCatalogLoader()

  const roots = ref<TreeNode[]>([])
  const expanded = ref<string[]>([])
  const loading = ref(false)
  const error = ref("")

  // Every node ever loaded, so a selection resolves to its kind without
  // walking the tree.
  const nodesById = ref(new Map<string, TreeNode>())
  const selectedId = ref<string | null>(null)

  const selected = computed(() =>
    selectedId.value === null ? null : (nodesById.value.get(selectedId.value) ?? null)
  )

  function remember(nodes: TreeNode[]) {
    for (const node of nodes) nodesById.value.set(node.id, node)
  }

  async function load() {
    roots.value = []
    expanded.value = []
    nodesById.value = new Map()
    selectedId.value = null
    error.value = ""
    loading.value = true
    try {
      roots.value = toTreeNodes(await loadChildren(connectorId.value, null))
      remember(roots.value)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
    } finally {
      loading.value = false
    }
  }

  /**
   * Re-read one branch after something changed it.
   *
   * Invalidating the query is not enough on its own: the tree keeps the
   * children on the node object, so they have to be put back as well.
   */
  async function reload(nodeId: string | null) {
    const node = nodeId === null ? null : (nodesById.value.get(nodeId) ?? null)
    const previous = node ? (node.children ?? []) : roots.value
    const wasHere = previous.some((child) => child.id === selectedId.value)

    const children = toTreeNodes(await loadChildren(connectorId.value, nodeId))
    remember(children)

    if (node) {
      node.children = children
      node.lazy = false
      if (!expanded.value.includes(node.id)) expanded.value = [...expanded.value, node.id]
    } else {
      roots.value = children
    }

    // A selection removed by the action must not linger: it would name a node
    // that is no longer there.
    if (wasHere && !children.some((child) => child.id === selectedId.value)) {
      selectedId.value = null
    }
  }

  async function onLazyLoad({
    node,
    done,
    fail,
  }: {
    node: TreeNode
    done: (children: TreeNode[]) => void
    fail: () => void
  }) {
    try {
      const children = toTreeNodes(await loadChildren(connectorId.value, node.id))
      remember(children)
      done(children)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
      fail()
    }
  }

  return { roots, expanded, selectedId, selected, loading, error, load, reload, onLazyLoad }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bun run test:unit -- src/features/catalog/useCatalogTree.spec.ts`
Expected: PASS, 4 теста.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalog/useCatalogTree.ts frontend/src/features/catalog/useCatalogTree.spec.ts
git commit -m "refactor(catalog): walking the tree is not logic of a dialog"
```

---

## Задача 11: союз панелей и реестр

**Files:**
- Create: `frontend/src/features/workspace/panels.ts`
- Create: `frontend/src/features/workspace/panels.spec.ts`

**Interfaces:**
- Consumes: `PanelLook` из `@/shared/workspace`.
- Produces:

```ts
export const panelSchema: ZodType<Panel>
export type Panel = ConnectorsPanel | CatalogPanel | RowsPanel
export type PanelKind = Panel["kind"]
export function kindOf(panel: Panel): PanelKind
export function lookOf(panel: Panel): PanelLook
export function componentOf(panel: Panel): Component
export function catalogPanelId(connectorId: string): string
export function rowsPanelId(connectorId: string, nodeId: string): string
```

Идентификаторы выводятся из того, что панель показывает, а не порождаются счётчиком: открыть ту же таблицу дважды должно активировать существующую вкладку, а не создать вторую.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/workspace/panels.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { catalogPanelId, componentOf, kindOf, lookOf, panelSchema, rowsPanelId } from "./panels"
import type { Panel, PanelKind } from "./panels"

const KINDS: PanelKind[] = ["connectors", "catalog", "rows"]

const samples: Record<PanelKind, Panel> = {
  connectors: { id: "connectors", kind: "connectors" },
  catalog: { id: catalogPanelId("c1"), kind: "catalog", connectorId: "c1", title: "local pg" },
  rows: {
    id: rowsPanelId("c1", "public.orders"),
    kind: "rows",
    connectorId: "c1",
    nodeId: "public.orders",
    title: "orders",
  },
}

describe("the panel registry", () => {
  it.each(KINDS)("has a component for %s", (kind) => {
    expect(componentOf(samples[kind])).toBeDefined()
  })

  it.each(KINDS)("has a title and an icon for %s", (kind) => {
    const look = lookOf(samples[kind])
    expect(look.title.length).toBeGreaterThan(0)
    expect(look.icon.length).toBeGreaterThan(0)
  })

  it.each(KINDS)("reports the kind of %s", (kind) => {
    expect(kindOf(samples[kind])).toBe(kind)
  })

  it.each(KINDS)("accepts a stored %s panel", (kind) => {
    expect(panelSchema.safeParse(samples[kind]).success).toBe(true)
  })

  it("refuses a panel of a kind it does not know", () => {
    expect(panelSchema.safeParse({ id: "x", kind: "sql" }).success).toBe(false)
  })

  it("refuses a rows panel with no node", () => {
    expect(
      panelSchema.safeParse({ id: "x", kind: "rows", connectorId: "c1", title: "t" }).success
    ).toBe(false)
  })

  it("gives the same panel of a table the same id every time", () => {
    expect(rowsPanelId("c1", "public.orders")).toBe(rowsPanelId("c1", "public.orders"))
    expect(rowsPanelId("c1", "public.orders")).not.toBe(rowsPanelId("c2", "public.orders"))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test:unit -- src/features/workspace/panels.spec.ts`
Expected: FAIL — `Failed to resolve import "./panels"`.

- [ ] **Step 3: Implement**

`frontend/src/features/workspace/panels.ts`:

```ts
import { z } from "zod"
import type { Component } from "vue"

import CatalogPanelView from "@/features/workspace/panels/CatalogPanel.vue"
import ConnectorsPanelView from "@/features/workspace/panels/ConnectorsPanel.vue"
import RowsPanelView from "@/features/workspace/panels/RowsPanel.vue"
import type { PanelLook } from "@/shared/workspace"

/**
 * What a panel is, and what renders it.
 *
 * The union is closed and the registry covers every member, so adding a kind
 * without a component fails to compile and fails the test beside this file.
 * The engine sees none of this — see the spec, W1.
 */

export const panelSchema = z.discriminatedUnion("kind", [
  z.object({ id: z.string(), kind: z.literal("connectors") }),
  z.object({
    id: z.string(),
    kind: z.literal("catalog"),
    connectorId: z.string(),
    title: z.string(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("rows"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
  }),
])

export type Panel = z.infer<typeof panelSchema>
export type PanelKind = Panel["kind"]

/**
 * A panel is identified by what it shows.
 *
 * Opening the same table twice then activates the tab that is already there
 * rather than putting a second copy of it beside the first.
 */
export const catalogPanelId = (connectorId: string) => `catalog:${connectorId}`
export const rowsPanelId = (connectorId: string, nodeId: string) => `rows:${connectorId}:${nodeId}`

export function kindOf(panel: Panel): PanelKind {
  return panel.kind
}

export function lookOf(panel: Panel): PanelLook {
  switch (panel.kind) {
    case "connectors":
      return { title: "Connections", icon: "lan" }
    case "catalog":
      return { title: panel.title, icon: "account_tree" }
    case "rows":
      return { title: panel.title, icon: "table_chart" }
  }
}

export function componentOf(panel: Panel): Component {
  switch (panel.kind) {
    case "connectors":
      return ConnectorsPanelView
    case "catalog":
      return CatalogPanelView
    case "rows":
      return RowsPanelView
  }
}
```

Замечание: тест не пройдёт, пока не существуют три компонента из задачи 12. Порядок: написать тест, увидеть падение на импорте, затем задача 12, затем вернуться и убедиться, что тест зелёный. Коммит — после задачи 12.

- [ ] **Step 4: Commit together with task 12**

Отдельного коммита у этой задачи нет: реестр без компонентов не собирается.

---

## Задача 12: три панели рабочей области

**Files:**
- Create: `frontend/src/features/workspace/panels/ConnectorsPanel.vue`
- Create: `frontend/src/features/workspace/panels/CatalogPanel.vue`
- Create: `frontend/src/features/workspace/panels/RowsPanel.vue`
- Create: `frontend/src/features/workspace/state.ts`
- Delete: `frontend/src/features/catalog/CatalogDialog.vue`

**Interfaces:**
- Consumes: `useCatalogTree` (задача 10), `ConnectorTable`, `ConnectorDialog`, `ActionBar`, `RowGrid`, `AppTree` (задача 9), `catalogPanelId`, `rowsPanelId` (задача 11).
- Produces: `state.ts` — тонкий мост между панелями:

```ts
export interface WorkspaceActions {
  openCatalog: (connectorId: string, title: string) => void
  openRows: (connectorId: string, nodeId: string, title: string) => void
}
export const workspaceActionsKey: InjectionKey<WorkspaceActions>
export function useWorkspaceActions(): WorkspaceActions
```

Панели не получают колбэки пропсами: `WorkspaceLeaf` рендерит `<component :is>` без пропсов, поэтому связь между панелями идёт через `provide`/`inject` от страницы.

- [ ] **Step 1: Write state.ts**

```ts
import { inject } from "vue"
import type { InjectionKey } from "vue"

/**
 * What one panel may ask the workspace to open.
 *
 * Provided by the page: the engine renders a panel with no props of its own,
 * and a panel has no business reaching into the layout.
 */
export interface WorkspaceActions {
  openCatalog: (connectorId: string, title: string) => void
  openRows: (connectorId: string, nodeId: string, title: string) => void
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
```

- [ ] **Step 2: Write ConnectorsPanel.vue**

Содержимое `ConnectorsPage.vue` без `AppLayout` и без `CatalogDialog`: «просмотреть» открывает панель каталога.

```vue
<script setup lang="ts">
import { computed, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
import ConnectorTable from "@/features/connectors/ConnectorTable.vue"
import { useCheckConnector, useConnectors, useDeleteConnector } from "@/features/connectors/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, useConfirm, useToast } from "@/shared/ui"

const confirm = useConfirm()
const toast = useToast()
const workspace = useWorkspaceActions()
const connectors = useConnectors()
const removeConnector = useDeleteConnector()
const checkConnector = useCheckConnector()

const dialogOpen = ref(false)
const editing = ref<ConnectorPublic | null>(null)

const rows = computed(() => connectors.data.value?.data ?? [])

function openCreate() {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(connector: ConnectorPublic) {
  editing.value = connector
  dialogOpen.value = true
}

async function check(connector: ConnectorPublic) {
  const result = await checkConnector.mutateAsync(connector.id)
  if (result.ok) {
    toast.success(`${result.message} (${String(result.latency_ms)} ms)`)
  } else {
    toast.error(result.message)
  }
}

async function confirmRemove(connector: ConnectorPublic) {
  const answer = await confirm({
    title: "Delete connection",
    message: `The connection "${connector.name}" will be deleted permanently.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!answer) return

  await removeConnector.mutateAsync(connector.id)
  toast.success("Connection deleted")
}
</script>

<template>
  <div class="connectors-panel">
    <div class="connectors-panel__bar">
      <AppButton
        icon="add"
        size="sm"
        label="New connection"
        data-testid="add-connector"
        @click="openCreate"
      />
    </div>

    <ConnectorTable
      :rows="rows"
      :loading="connectors.isLoading.value"
      @edit="openEdit"
      @remove="confirmRemove"
      @check="check"
      @browse="workspace.openCatalog($event.id, $event.name)"
    />

    <ConnectorDialog
      v-model="dialogOpen"
      :connector="editing"
    />
  </div>
</template>

<style scoped>
.connectors-panel {
  padding: 8px;
}
.connectors-panel__bar {
  margin-bottom: 8px;
}
</style>
```

- [ ] **Step 3: Write CatalogPanel.vue**

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import ActionBar from "@/features/catalog/ActionBar.vue"
import { useCatalogTree } from "@/features/catalog/useCatalogTree"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppBanner, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"

const props = defineProps<{ connectorId: string }>()

const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const tree = useCatalogTree(connectorId)

onMounted(() => {
  void tree.load()
})

const targetLabel = computed(() => tree.selected.value?.label ?? "Whole connection")

/** Selecting a readable node opens it in the section that holds rows. */
function onSelected(nodeId: string | null) {
  tree.selectedId.value = nodeId
  const node = tree.selected.value
  if (node !== null && node.readable) {
    workspace.openRows(props.connectorId, node.id, node.label)
  }
}
</script>

<template>
  <div class="catalog-panel">
    <AppBanner
      v-if="tree.error.value"
      tone="error"
      data-testid="catalog-error"
    >
      {{ tree.error.value }}
    </AppBanner>

    <ActionBar
      v-if="!tree.loading.value"
      :connector-id="connectorId"
      :node-id="tree.selectedId.value"
      :node-label="targetLabel"
      @done="tree.reload"
    />

    <AppSpinner v-if="tree.loading.value" />

    <!-- The tree has no caption prop, so the header is rendered here: the
         default one would show the label alone and silently drop the data type
         and the row estimate. -->
    <AppTree
      v-else-if="tree.roots.value.length"
      v-model:expanded="tree.expanded.value"
      :nodes="tree.roots.value"
      :selected="tree.selectedId.value"
      node-key="id"
      data-testid="catalog-tree"
      @update:selected="onSelected"
      @lazy-load="tree.onLazyLoad"
    >
      <template #default-header="{ node }">
        <q-icon
          :name="node.icon"
          size="20px"
          class="q-mr-sm"
        />
        <span>{{ node.label }}</span>
        <span
          v-if="node.caption"
          class="text-caption text-grey q-ml-sm"
        >
          {{ node.caption }}
        </span>
      </template>
    </AppTree>

    <AppEmptyState
      v-else-if="!tree.error.value"
      text="Nothing to show"
    />
  </div>
</template>

<style scoped>
.catalog-panel {
  padding: 8px;
}
</style>
```

- [ ] **Step 4: Write RowsPanel.vue**

```vue
<script setup lang="ts">
import RowGrid from "@/features/catalog/RowGrid.vue"

/**
 * One relation, in its own tab.
 *
 * The row estimate is not passed on: it belongs to the catalog node, and a
 * panel restored from storage has not read the catalog. The grid pages by
 * has_more when it has no estimate, which is what a file source gives it too.
 */
defineProps<{ connectorId: string; nodeId: string }>()
</script>

<template>
  <div class="rows-panel">
    <RowGrid
      :connector-id="connectorId"
      :node-id="nodeId"
    />
  </div>
</template>

<style scoped>
.rows-panel {
  padding: 8px;
}
</style>
```

- [ ] **Step 5: Make the panels receive their props**

`WorkspaceLeaf` рендерит `<component :is>` без пропсов, а `CatalogPanel` и `RowsPanel` их требуют. Расширить `componentOf` в `panels.ts` так, чтобы он возвращал компонент с уже привязанными пропсами:

```ts
import { h } from "vue"

export function componentOf(panel: Panel): Component {
  switch (panel.kind) {
    case "connectors":
      return ConnectorsPanelView
    case "catalog":
      // The engine renders a panel with no props of its own, so what a panel
      // needs is bound here, where the panel is still a typed object.
      return () => h(CatalogPanelView, { connectorId: panel.connectorId })
    case "rows":
      return () => h(RowsPanelView, { connectorId: panel.connectorId, nodeId: panel.nodeId })
  }
}
```

- [ ] **Step 6: Delete the dialog**

```bash
git rm frontend/src/features/catalog/CatalogDialog.vue
```

`ConnectorsPage.vue` пока на него ссылается и сломается — чинится задачей 13, которая идёт в том же коммите.

- [ ] **Step 7: Run the registry test**

Run: `bun run test:unit -- src/features/workspace/panels.spec.ts`
Expected: PASS, 13 тестов.

- [ ] **Step 8: Commit with task 13**

Коммит выполняется в конце задачи 13, когда страница уже собрана.

---

## Задача 13: страница рабочей области

**Files:**
- Create: `frontend/src/features/workspace/WorkspacePage.vue`
- Modify: `frontend/src/router/index.ts`
- Delete: `frontend/src/features/connectors/ConnectorsPage.vue`

**Interfaces:**
- Consumes: всё из задач 6–12.
- Produces: маршрут `/` с `name: "workspace"`. Прежнее имя маршрута `connectors` использовалось в `router.beforeEach` — заменить оба вхождения.

- [ ] **Step 1: Write WorkspacePage.vue**

```vue
<script setup lang="ts">
import { provide } from "vue"

import {
  catalogPanelId,
  componentOf,
  kindOf,
  lookOf,
  panelSchema,
  rowsPanelId,
} from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { workspaceActionsKey } from "@/features/workspace/state"
import { AppLayout } from "@/shared/ui"
import { makeLeaf, makeSplit, useWorkspace, WorkspaceRoot } from "@/shared/workspace"

/**
 * The workspace: connections, a catalog and the data of one node, side by side.
 *
 * The layout is the user's own from the second visit onwards; the default is
 * only what the first one looks like.
 */
const workspace = useWorkspace<Panel>({
  storageKey: "dataplayer-workspace",
  panelSchema,
  defaults: () => ({
    tree: makeSplit(
      "root",
      "row",
      [makeLeaf("connections", ["connectors"]), makeLeaf("data", ["connectors-hint"])],
      [32, 68]
    ),
    panels: [{ id: "connectors", kind: "connectors" }],
  }),
  kindOf,
  look: lookOf,
  component: componentOf,
})

provide(workspaceActionsKey, {
  openCatalog: (connectorId: string, title: string) => {
    workspace.open({ id: catalogPanelId(connectorId), kind: "catalog", connectorId, title })
  },
  openRows: (connectorId: string, nodeId: string, title: string) => {
    workspace.open({
      id: rowsPanelId(connectorId, nodeId),
      kind: "rows",
      connectorId,
      nodeId,
      title,
    })
  },
})
</script>

<template>
  <AppLayout fill>
    <WorkspaceRoot :context="workspace.context" />
  </AppLayout>
</template>
```

**Раскладка по умолчанию — один лист.** Три секции нельзя выложить заранее: панель каталога описывает конкретное соединение, а его пользователь ещё не выбрал, и панель без соединения нечему показывать. Поэтому `defaults` в коде выше читается так:

```ts
  defaults: () => ({
    tree: makeLeaf("connections", ["connectors"]),
    panels: [{ id: "connectors", kind: "connectors" }],
  }),
```

и импорт `makeSplit` из этого файла не нужен.

Секции появляются по мере работы: пользователь открывает каталог, `leafForKind` не находит секции с панелями вида `catalog`, берёт лист с фокусом, и каталог встаёт вкладкой рядом; перетаскивание вкладки на край разводит их по двум секциям, а таблица — по третьей. Это отличается от «трёх панелей с первого открытия» и записывается в «Известные отклонения» задачей 14.

- [ ] **Step 2: Point the router at it**

В `frontend/src/router/index.ts` заменить запись маршрута `/`:

```ts
    {
      path: "/",
      name: "workspace",
      component: () => import("@/features/workspace/WorkspacePage.vue"),
      meta: { requiresAuth: true },
    },
```

и в `router.beforeEach` заменить `return { name: "connectors" }` на `return { name: "workspace" }`.

- [ ] **Step 3: Delete the old page**

```bash
git rm frontend/src/features/connectors/ConnectorsPage.vue
```

- [ ] **Step 4: Run everything**

Run: `bun run test:unit && bun run lint && bun run type-check`
Expected: чисто. Если `lint` жалуется на `q-tree` — значит `CatalogDialog.vue` не удалён.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/workspace frontend/src/router/index.ts
git add -u
git commit -m "feat(workspace): the main screen is a workspace, not a table with a modal"
```

---

## Задача 14: сквозные сценарии и документы

**Files:**
- Modify: `frontend/tests/catalog.spec.ts`
- Modify: `frontend/tests/rows.spec.ts`
- Modify: `frontend/tests/files.spec.ts`
- Modify: `frontend/tests/actions.spec.ts`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `data-testid` из задачи 7 и существующие из `ConnectorTable`.

- [ ] **Step 1: Run the existing scenarios and read the failures**

Run: `bunx playwright test`
Expected: FAIL. Сценарии открывают каталог кнопкой `browse-{name}` и закрывают кнопкой `Close` диалога, которой больше нет.

- [ ] **Step 2: Adjust each scenario to the workspace**

Замена, одна и та же в четырёх файлах: `await page.getByRole("button", { name: "Close" }).click()` уходит; вместо него вкладка каталога закрывается своим крестом, а идентификатор вкладки выводится так же, как в `panels.ts`:

```ts
/** The catalog tab of a connector, addressed the way panels.ts names it. */
async function closeCatalog(page: import("@playwright/test").Page, connectorId: string) {
  await page.getByTestId(`workspace-close-catalog:${connectorId}`).click()
}
```

Идентификатор соединения в сценарии неизвестен — он приходит с сервера. Поэтому проще закрывать по заголовку вкладки:

```ts
async function closeCatalogTab(page: import("@playwright/test").Page, name: string) {
  await page
    .locator('[data-testid^="workspace-tab-catalog:"]', { hasText: name })
    .getByRole("button")
    .click()
}
```

Крест внутри вкладки — `<span>`, а не кнопка, поэтому обращение к нему:

```ts
  await page
    .locator('[data-testid^="workspace-tab-catalog:"]', { hasText: name })
    .locator('[data-testid^="workspace-close-"]')
    .click()
```

Открытие каталога остаётся прежним: `await page.getByTestId(\`browse-${name}\`).click()`.

Просмотр строк: раньше выбор узла в дереве показывал сетку в том же диалоге; теперь он открывает вкладку. Ожидание в `rows.spec.ts` и `files.spec.ts` — сначала появление вкладки, затем содержимое:

```ts
  await page.locator(".q-tree__node-header", { hasText: "pg_class" }).first().click()
  await expect(page.locator('[data-testid^="workspace-tab-rows:"]')).toBeVisible()
  await expect(page.getByTestId("row-grid")).toContainText("relname")
```

- [ ] **Step 3: Write the workspace scenario**

Дописать в `frontend/tests/workspace.spec.ts`:

```ts
import { login } from "./utils/login"

test("opens a table beside the connections and keeps it across a reload", async ({ page }) => {
  await login(page)

  // Whatever the previous run left is not this test's subject.
  await page.evaluate(() => localStorage.removeItem("dataplayer-workspace"))
  await page.reload()

  await expect(page.getByTestId("connector-table")).toBeVisible()
  await expect(page.getByTestId("workspace-tab-connectors")).toBeVisible()
})
```

Полный сценарий «соединение → каталог → таблица → перезагрузка» уже покрыт `rows.spec.ts` после правки шага 2; здесь проверяется только то, что рабочая область — это первое, что видит вошедший пользователь.

- [ ] **Step 4: Run the whole browser suite**

Run: `bunx playwright test`
Expected: PASS. Перед прогоном поднять стенд:

```bash
docker compose up -d db backend
```

- [ ] **Step 5: Update AGENTS.md**

В разделе «What exists» в дереве `frontend/src` добавить:

```
├── shared/
│   ├── workspace/       the panel engine: a layout tree, tabs, drag and drop;
│   │                    tree.ts, dropZone.ts, placement.ts and persist.ts are
│   │                    pure, the components see one injected context
└── features/
    └── workspace/       the three panels and what may be opened from one
```

В «Decisions that shape the code» добавить D12 со ссылкой на спеку:

```markdown
**D12. The screen is a workspace of sections, and the engine behind it knows
nothing about the application.** A layout is a tree of sections; every change
to it is a pure function; a section is a list of panels with one active, and
that is the only notion of a tab in the application. What a panel is belongs to
`features/workspace`, which hands the engine a component and a look per panel.
Full reasoning in `docs/superpowers/specs/2026-08-22-workspace-design.md`.

The old application had such an engine and it grew to 2438 lines: nodes were
mutated in place and carried parent back-pointers, so undoing anything needed a
history of layouts and a command language of nine verbs, and a node it could
not remove had to be left in place marked `fake`.
```

В «Known deviations» добавить:

```markdown
- **The default layout is one section, not three.** A workspace opens showing
  connections alone; the catalog and a table arrive as tabs beside them and are
  pulled apart by dragging. Seeding three sections would mean seeding panels
  for a connector the user has not chosen yet.
- **Tabs cannot be reordered inside a strip.** Dragging a tab moves it to
  another section or splits one; dropping it back into its own strip does
  nothing.
- **The layout is one per browser.** It lives in localStorage, so it does not
  follow a user to another machine and is not shared between two windows.
- **A panel of a connector that was deleted stays until it is closed.** It
  shows the error the server gave rather than disappearing, because the panel
  cannot tell a deleted connector from a failed request.
```

В «What comes next» отметить, что подпроект 7а закрыт, и `q-tree` больше не отклонение — удалить строку «**`q-tree` is outside the kit**».

- [ ] **Step 6: Check the diff before committing**

Run: `git diff --stat && git show :AGENTS.md | file -`
Expected: диффы соразмерны правкам; AGENTS.md не переписан целиком из-за смены переводов строк.

- [ ] **Step 7: Commit**

```bash
git add frontend/tests AGENTS.md
git commit -m "test(workspace): the browser suite works the workspace, not the modal"
```

---

## Самопроверка плана

**Покрытие спеки:**

| Решение спеки | Задача |
| --- | --- |
| W1 движок не знает предметной области | 6 (контекст), 11 (реестр) |
| W2 размеченный союз | 1 |
| W3 чистые функции | 1–3 |
| W4 нормализация | 2 |
| W5 minSize в пикселях | 3 (`resizeSplit`), 7 (`WorkspaceNode.onMove`) |
| W6 свёрнутость — поле листа | 3, 7 (`styleFor`) |
| W7 pointer events и зоны | 4, 7 |
| W8 секция это вкладки | 7 (`WorkspaceLeaf`) |
| W9 сохранённое — недоверенный ввод | 5 |
| W10 панель исчезнувшего объекта | 12 (`RowsPanel` через `RowGrid`), 14 (запись в отклонения) |
| W11 куда открывается панель | 4 (`leafForKind`), 6 |
| `AppTree` в ките | 9 |
| `useCatalogTree` отдельно от диалога | 10 |
| Удаление `CatalogDialog` | 12 |

**Согласованность имён:** `LayoutNode`, `LeafNode`, `SplitNode`, `NodeId`, `PanelId`, `DropZone`, `MIN_PANEL_PX`, `COLLAPSED_PX`, `makeLeaf`, `makeSplit`, `nextId`, `nodeAt`, `pathOfNode`, `pathOfPanel`, `leavesOf`, `replaceAt`, `normalize`, `addPanel`, `removePanel`, `activatePanel`, `setCollapsed`, `resizeSplit`, `splitLeaf`, `movePanel`, `dropZoneAt`, `leafForKind`, `serializeWorkspace`, `parseWorkspace`, `WORKSPACE_VERSION`, `workspaceKey`, `WorkspaceContext`, `useWorkspace`, `panelSchema`, `kindOf`, `lookOf`, `componentOf`, `catalogPanelId`, `rowsPanelId`, `workspaceActionsKey`, `useWorkspaceActions` — одни и те же во всех задачах.

**Две поправки, найденные при написании плана и внесённые в спеку:**

1. `storedSize` в `LeafNode` не нужен: сворачивание не трогает `sizes`, поэтому прежний размер уже там.
2. Правило «куда открывается панель» читается из дерева, без отдельной истории.

**Третья поправка, которую внести в спеку при выполнении задачи 13:** раскладка по умолчанию — один лист, а не три секции. Три секции нельзя задать заранее, не выдумав панели для соединения, которое пользователь ещё не выбрал.
