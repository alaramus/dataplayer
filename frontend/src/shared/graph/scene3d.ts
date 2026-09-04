import * as THREE from "three"
import { OrbitControls } from "three/addons/controls/OrbitControls.js"

import { accentIndex, edgesOf, neighborsOf } from "./model"
import type { Camera3, GraphDocument, GraphSelection, Point3 } from "./model"

interface SceneEvents {
  select: (selection: GraphSelection) => void
  activate: (id: string) => void
  move: (id: string, point: Point3) => void
  camera: (camera: Camera3) => void
  unavailable: () => void
}
const point = (value: Point3) => new THREE.Vector3(value.x, value.y, value.z)
const plain = (value: THREE.Vector3): Point3 => ({ x: value.x, y: value.y, z: value.z })

/** All GPU resources and input handlers belong to this one mounted surface. */
export class GraphScene {
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera = new THREE.PerspectiveCamera(45, 1, 1, 1_000_000)
  private readonly controls: OrbitControls
  private readonly objects = new THREE.Group()
  private readonly edges = new THREE.Group()
  private readonly nodes = new Map<string, THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>>()
  private readonly labels = new Map<string, THREE.Sprite>()
  private readonly picks = new WeakMap<THREE.Object3D, GraphSelection>()
  private readonly ray = new THREE.Raycaster()
  private readonly handlers = new AbortController()
  private readonly resizeObserver: ResizeObserver
  private readonly themeObserver: MutationObserver
  private graph: GraphDocument = { nodes: [], edges: [], groups: [] }
  private positions: Record<string, Point3> = {}
  private selection: GraphSelection = null
  private showLabels = true
  private active = true
  private disposed = false
  private frame = 0
  private press: { x: number; y: number } | null = null
  private drag: { id: string; pointer: number; plane: THREE.Plane; offset: THREE.Vector3; original: Point3 } | null = null

  constructor(private readonly root: HTMLElement, private readonly events: SceneEvents, saved: Camera3 | null) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.domElement.setAttribute("aria-label", "3D graph. Drag to orbit, scroll to zoom, Shift-drag a node to move it.")
    this.renderer.domElement.setAttribute("data-testid", "graph-3d-canvas")
    root.append(this.renderer.domElement)
    this.scene.add(this.objects, this.edges, new THREE.HemisphereLight(0xffffff, 0x445566, 2.4))
    const light = new THREE.DirectionalLight(0xffffff, 2)
    light.position.set(200, 600, 400)
    this.scene.add(light)
    this.camera.position.set(400, 500, 700)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.minDistance = 50
    this.controls.maxDistance = 500_000
    this.controls.enableDamping = false
    this.controls.addEventListener("change", this.render)
    this.controls.addEventListener("end", this.saveCamera)
    if (saved) this.restoreCamera(saved)
    this.ray.params.Line = { threshold: 7 }
    this.resizeObserver = new ResizeObserver(this.resize)
    this.resizeObserver.observe(root)
    this.themeObserver = new MutationObserver(() => this.rebuild())
    this.themeObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] })
    const options = { signal: this.handlers.signal }
    this.renderer.domElement.addEventListener("pointerdown", this.down, { ...options, capture: true })
    this.renderer.domElement.addEventListener("pointermove", this.pointerMove, { ...options, capture: true })
    this.renderer.domElement.addEventListener("pointerup", this.up, { ...options, capture: true })
    this.renderer.domElement.addEventListener("pointercancel", this.cancelDrag, options)
    this.renderer.domElement.addEventListener("lostpointercapture", this.cancelDrag, options)
    this.renderer.domElement.addEventListener("dblclick", this.doubleClick, options)
    this.renderer.domElement.addEventListener("webglcontextlost", this.contextLost, options)
    root.addEventListener("keydown", this.keyDown, options)
    this.resize()
  }

  private color(name: string): string { return getComputedStyle(this.root).getPropertyValue(name).trim() }
  setGraph(graph: GraphDocument, positions: Record<string, Point3>) {
    this.graph = graph
    this.positions = positions
    this.rebuild()
  }
  setPositions(positions: Record<string, Point3>) {
    this.positions = positions
    for (const [id, mesh] of this.nodes) {
      const position = positions[id]
      if (!position) continue
      mesh.position.copy(point(position))
      this.labels.get(id)?.position.copy(mesh.position).add(new THREE.Vector3(0, 63, 0))
    }
    this.buildEdges()
    this.highlight()
  }
  setSelection(selection: GraphSelection) { this.selection = selection; this.highlight() }
  setLabels(show: boolean) { this.showLabels = show; for (const label of this.labels.values()) label.visible = show; this.render() }
  setActive(active: boolean) {
    this.active = active
    this.controls.enabled = active
    if (!active) { this.cancelDrag(); cancelAnimationFrame(this.frame); this.frame = 0 }
    else this.resize()
  }
  restoreCamera(saved: Camera3) {
    this.camera.position.copy(point(saved.position))
    this.controls.target.copy(point(saved.target))
    this.controls.update()
    this.render()
  }
  fit() {
    if (!this.nodes.size) return
    const box = new THREE.Box3().setFromPoints([...this.nodes.values()].map((mesh) => mesh.position)).expandByScalar(100)
    const center = box.getCenter(new THREE.Vector3())
    const radius = box.getSize(new THREE.Vector3()).length() / 2
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2)) / Math.min(1, this.camera.aspect)
    this.controls.target.copy(center)
    this.camera.position.copy(center).add(new THREE.Vector3(0.6, 0.8, 1).normalize().multiplyScalar(distance))
    this.controls.update()
    this.saveCamera()
  }
  zoom(factor: number) {
    const offset = this.camera.position.clone().sub(this.controls.target)
    offset.setLength(Math.max(50, Math.min(500_000, offset.length() / factor)))
    this.camera.position.copy(this.controls.target).add(offset)
    this.controls.update()
    this.saveCamera()
  }
  focus(id: string) {
    const node = this.nodes.get(id)
    if (!node) return
    const offset = this.camera.position.clone().sub(this.controls.target).normalize().multiplyScalar(420)
    this.controls.target.copy(node.position)
    this.camera.position.copy(node.position).add(offset)
    this.controls.update()
    this.saveCamera()
  }
  private rebuild() {
    if (this.disposed) return
    this.clear(this.objects)
    this.nodes.clear()
    this.labels.clear()
    this.scene.background = new THREE.Color(this.color("--dp-chrome-raised"))
    for (const node of this.graph.nodes) {
      const material = new THREE.MeshStandardMaterial({ color: this.color(`--dp-chart-${accentIndex(node)}`), roughness: 0.6, metalness: 0.1, transparent: true })
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(110, 64, 64), material)
      mesh.position.copy(point(this.positions[node.id]!))
      this.nodes.set(node.id, mesh)
      this.picks.set(mesh, { kind: "node", id: node.id })
      this.objects.add(mesh)
      const canvas = document.createElement("canvas")
      canvas.width = 512; canvas.height = 96
      const ctx = canvas.getContext("2d")
      if (!ctx) continue
      ctx.fillStyle = this.color("--dp-surface")
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = this.color("--dp-graph-label")
      ctx.font = "600 28px sans-serif"
      ctx.textAlign = "center"
      const title = node.label.length > 30 ? `${node.label.slice(0, 29)}…` : node.label
      ctx.fillText(title, 256, 40, 490)
      ctx.font = "22px sans-serif"
      ctx.fillText(node.caption ?? "", 256, 75, 490)
      const texture = new THREE.CanvasTexture(canvas)
      texture.colorSpace = THREE.SRGBColorSpace
      const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: true }))
      label.scale.set(240, 45, 1)
      label.position.copy(mesh.position).add(new THREE.Vector3(0, 63, 0))
      label.visible = this.showLabels
      this.labels.set(node.id, label)
      this.picks.set(label, { kind: "node", id: node.id })
      this.objects.add(label)
    }
    this.buildEdges()
    this.highlight()
  }
  private buildEdges() {
    this.clear(this.edges)
    const lanes = new Map<string, number>()
    for (const edge of this.graph.edges) {
      const a = point(this.positions[edge.source.nodeId]!)
      const b = point(this.positions[edge.target.nodeId]!)
      const key = JSON.stringify([edge.source.nodeId, edge.target.nodeId].sort())
      const lane = lanes.get(key) ?? 0
      lanes.set(key, lane + 1)
      let curve: THREE.CubicBezierCurve3
      if (a.distanceTo(b) < 1) {
        curve = new THREE.CubicBezierCurve3(a.clone().add(new THREE.Vector3(55, 0, 0)), a.clone().add(new THREE.Vector3(180 + lane * 30, 150, 0)), b.clone().add(new THREE.Vector3(-180 - lane * 30, 150, 0)), b.clone().add(new THREE.Vector3(-55, 0, 0)))
      } else {
        const direction = b.clone().sub(a).normalize()
        a.addScaledVector(direction, 58); b.addScaledVector(direction, -58)
        const lift = new THREE.Vector3(0, 45 + lane * 40, 0)
        curve = new THREE.CubicBezierCurve3(a, a.clone().lerp(b, 0.3).add(lift), a.clone().lerp(b, 0.7).add(lift), b)
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(24))
      const material = edge.dashed
        ? new THREE.LineDashedMaterial({ color: this.color("--dp-graph-edge"), dashSize: 8, gapSize: 5, transparent: true })
        : new THREE.LineBasicMaterial({ color: this.color("--dp-graph-edge"), transparent: true })
      const line = new THREE.Line(geometry, material)
      line.computeLineDistances()
      this.picks.set(line, { kind: "edge", id: edge.id })
      this.edges.add(line)
      if (edge.directed) {
        const arrow = new THREE.Mesh(new THREE.ConeGeometry(5, 15, 8), new THREE.MeshBasicMaterial({ color: this.color("--dp-graph-edge"), transparent: true }))
        arrow.position.copy(curve.getPoint(0.96))
        arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), curve.getTangent(0.96).normalize())
        this.picks.set(arrow, { kind: "edge", id: edge.id })
        this.edges.add(arrow)
      }
    }
  }
  private highlight() {
    const neighbors = neighborsOf(this.graph, this.selection)
    const selectedEdges = new Set(edgesOf(this.graph, this.selection).map((edge) => edge.id))
    for (const node of this.graph.nodes) {
      const mesh = this.nodes.get(node.id)!
      const dim = this.selection && !neighbors.has(node.id)
      mesh.material.opacity = dim ? 0.16 : node.placeholder ? 0.45 : 1
      mesh.material.emissive.copy(mesh.material.color).multiplyScalar(neighbors.has(node.id) ? 0.3 : 0)
      const label = this.labels.get(node.id)
      if (label) label.material.opacity = dim ? 0.2 : 1
    }
    for (const object of this.edges.children) {
      const selected = this.picks.get(object)
      if (!(object instanceof THREE.Line || object instanceof THREE.Mesh) || Array.isArray(object.material)) continue
      const material = object.material as THREE.LineBasicMaterial | THREE.MeshBasicMaterial
      const active = selected?.kind === "edge" && selectedEdges.has(selected.id)
      material.opacity = this.selection && !active ? 0.12 : 1
      material.color.set(this.color(active ? "--q-primary" : "--dp-graph-edge"))
    }
    this.render()
  }
  private aim(event: PointerEvent | MouseEvent) {
    const bounds = this.renderer.domElement.getBoundingClientRect()
    this.ray.setFromCamera(new THREE.Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1), this.camera)
  }
  private picked(event: PointerEvent | MouseEvent): GraphSelection {
    this.aim(event)
    const hit = this.ray.intersectObjects([...this.objects.children, ...this.edges.children], false).find((item) => item.object.visible && this.picks.has(item.object))
    return hit ? this.picks.get(hit.object) ?? null : null
  }
  private down = (event: PointerEvent) => {
    if (event.button !== 0 || !event.isPrimary) return
    this.press = { x: event.clientX, y: event.clientY }
    if (!event.shiftKey) return
    const selected = this.picked(event)
    if (selected?.kind !== "node") return
    event.stopImmediatePropagation()
    const original = this.positions[selected.id]!
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(this.camera.getWorldDirection(new THREE.Vector3()), point(original))
    const hit = this.ray.ray.intersectPlane(plane, new THREE.Vector3())
    if (!hit) return
    this.drag = { id: selected.id, pointer: event.pointerId, plane, offset: point(original).sub(hit), original: { ...original } }
    this.controls.enabled = false
    this.renderer.domElement.setPointerCapture(event.pointerId)
    this.events.select(selected)
  }
  private pointerMove = (event: PointerEvent) => {
    if (!this.drag || event.pointerId !== this.drag.pointer) return
    event.stopImmediatePropagation()
    this.aim(event)
    const hit = this.ray.ray.intersectPlane(this.drag.plane, new THREE.Vector3())
    if (hit) this.events.move(this.drag.id, plain(hit.add(this.drag.offset)))
  }
  private up = (event: PointerEvent) => {
    if (this.drag) {
      event.stopImmediatePropagation()
      const pointer = this.drag.pointer
      this.drag = null
      this.controls.enabled = this.active
      if (this.renderer.domElement.hasPointerCapture(pointer)) this.renderer.domElement.releasePointerCapture(pointer)
    } else if (this.press && Math.hypot(event.clientX - this.press.x, event.clientY - this.press.y) < 4) this.events.select(this.picked(event))
    this.press = null
  }
  private cancelDrag = () => {
    const drag = this.drag
    this.drag = null; this.press = null
    this.controls.enabled = this.active
    if (drag) {
      this.events.move(drag.id, drag.original)
      if (this.renderer.domElement.hasPointerCapture(drag.pointer)) this.renderer.domElement.releasePointerCapture(drag.pointer)
    }
  }
  private keyDown = (event: KeyboardEvent) => { if (event.key === "Escape") this.cancelDrag() }
  private doubleClick = (event: MouseEvent) => { const selected = this.picked(event); if (selected?.kind === "node") this.events.activate(selected.id) }
  private contextLost = (event: Event) => { event.preventDefault(); this.events.unavailable() }
  private saveCamera = () => { if (!this.disposed) this.events.camera({ position: plain(this.camera.position), target: plain(this.controls.target) }) }
  private resize = () => {
    if (this.disposed || !this.active || !this.root.clientWidth || !this.root.clientHeight) return
    this.renderer.setSize(this.root.clientWidth, this.root.clientHeight)
    this.camera.aspect = this.root.clientWidth / this.root.clientHeight
    this.camera.updateProjectionMatrix()
    this.render()
  }
  private render = () => {
    if (this.frame || !this.active || this.disposed) return
    this.frame = requestAnimationFrame(() => {
      this.frame = 0
      if (this.active && this.root.clientWidth && this.root.clientHeight) this.renderer.render(this.scene, this.camera)
    })
  }
  private clear(group: THREE.Group) {
    group.traverse((object) => {
      if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Sprite)) return
      if (object instanceof THREE.Mesh || object instanceof THREE.Line) object.geometry.dispose()
      const materials: THREE.Material[] = Array.isArray(object.material) ? object.material : [object.material]
      for (const material of materials) {
        if (material instanceof THREE.SpriteMaterial) material.map?.dispose()
        material.dispose()
      }
    })
    group.clear()
  }
  dispose() {
    this.cancelDrag()
    this.disposed = true
    cancelAnimationFrame(this.frame)
    this.handlers.abort()
    this.resizeObserver.disconnect()
    this.themeObserver.disconnect()
    this.controls.dispose()
    this.clear(this.objects); this.clear(this.edges)
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.renderer.domElement.remove()
  }
}
