import { describe, expect, it } from "vitest"

import { freshProjectName } from "./projectName"

describe("the name a new project is offered", () => {
  it("is New project while nothing is called that", () => {
    expect(freshProjectName([])).toBe("New project")
    expect(freshProjectName(["Reports"])).toBe("New project")
  })

  it("is numbered once the name is taken, with the first free number", () => {
    expect(freshProjectName(["New project"])).toBe("New project 2")
    expect(freshProjectName(["New project", "New project 2"])).toBe("New project 3")
    expect(freshProjectName(["New project", "New project 3"])).toBe("New project 2")
  })
})
