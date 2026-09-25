declare module "d3-force-3d" {
  interface Node3D {
    x?: number
    y?: number
    z?: number
  }

  interface Simulation<T extends Node3D> {
    force(name: string, force: unknown): Simulation<T>
    stop(): Simulation<T>
    tick(iterations?: number): Simulation<T>
  }

  interface LinkForce<T> {
    id(accessor: (node: T) => string): LinkForce<T>
    distance(value: number): LinkForce<T>
    strength(value: number): LinkForce<T>
  }

  interface ManyBodyForce {
    strength(value: number): ManyBodyForce
  }

  interface CollisionForce {
    strength(value: number): CollisionForce
    iterations(value: number): CollisionForce
  }

  interface PositionForce<T> {
    strength(value: number): PositionForce<T>
  }

  export function forceSimulation<T extends Node3D>(nodes: T[], dimensions: 1 | 2 | 3): Simulation<T>
  export function forceLink<T extends Node3D, L>(links: L[]): LinkForce<T>
  export function forceManyBody(): ManyBodyForce
  export function forceCollide(radius: number): CollisionForce
  export function forceCenter(x: number, y: number, z: number): unknown
  export function forceX<T extends Node3D>(position: (node: T) => number): PositionForce<T>
  export function forceZ<T extends Node3D>(position: (node: T) => number): PositionForce<T>
}
