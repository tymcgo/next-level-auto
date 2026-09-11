// WorkflowState.ts — Durable Object for tracking workflow execution state
// Each workflow instance gets its own Durable Object for isolation and consistency

import { DurableObject } from "cloudflare:workers";

export interface WorkflowDefinition {
  name: string
  version: string
  states: string[]
  initial_state: string
  transitions: Record<string, { event: string; target: string; guard?: string }[]>
  required_outcomes: string[]
  sla_minutes: number
}

export interface WorkflowInstance {
  id: string
  definition: WorkflowDefinition
  current_state: string
  context: Record<string, any>
  history: { state: string; timestamp: string; event?: string }[]
  created_at: string
  updated_at: string
  expires_at: string
}

export class WorkflowState extends DurableObject {
  private sql: SqlStorage

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env)
    this.sql = ctx.storage.sql
    this.initializeDatabase()
  }

  private initializeDatabase() {
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS workflow_instances (
        id TEXT PRIMARY KEY,
        definition TEXT NOT NULL,
        current_state TEXT NOT NULL,
        context TEXT NOT NULL DEFAULT '{}',
        history TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_workflow_expires ON workflow_instances(expires_at);
    `)
  }

  // Create a new workflow instance
  async create(instance: WorkflowInstance): Promise<{ success: boolean; error?: string }> {
    try {
      this.sql.exec(
        `INSERT INTO workflow_instances (id, definition, current_state, context, history, created_at, updated_at, expires_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        instance.id,
        JSON.stringify(instance.definition),
        instance.current_state,
        JSON.stringify(instance.context),
        JSON.stringify(instance.history),
        instance.created_at,
        instance.updated_at,
        instance.expires_at
      )
      return { success: true }
    } catch (e: any) {
      if (e.message?.includes("UNIQUE constraint")) {
        return { success: false, error: "Workflow instance already exists" }
      }
      throw e
    }
  }

  // Get current state
  async getState(id: string): Promise<WorkflowInstance | null> {
    const result = this.sql.exec(
      "SELECT * FROM workflow_instances WHERE id = ?",
      id
    ).toArray()

    if (result.length === 0) return null

    const row = result[0]
    return {
      id: row.id as string,
      definition: JSON.parse(row.definition as string),
      current_state: row.current_state as string,
      context: JSON.parse(row.context as string),
      history: JSON.parse(row.history as string),
      created_at: row.created_at as string,
      updated_at: row.updated_at as string,
      expires_at: row.expires_at as string,
    }
  }

  // Transition to a new state
  async transition(
    id: string,
    event: string,
    newState: string,
    contextUpdate?: Record<string, any>
  ): Promise<{ success: boolean; error?: string }> {
    const instance = await this.getState(id)
    if (!instance) {
      return { success: false, error: "Workflow instance not found" }
    }

    // Check if current state is final
    if (instance.definition.states.indexOf(instance.current_state) === -1) {
      return { success: false, error: "Current state is not valid" }
    }

    // Update state
    const now = new Date().toISOString()
    const newHistory = [
      ...instance.history,
      { state: newState, timestamp: now, event },
    ]

    const newContext = { ...instance.context, ...contextUpdate }

    this.sql.exec(
      `UPDATE workflow_instances 
       SET current_state = ?, context = ?, history = ?, updated_at = ?
       WHERE id = ?`,
      newState,
      JSON.stringify(newContext),
      JSON.stringify(newHistory),
      now,
      id
    )

    return { success: true }
  }

  // List all instances in a given state
  async listByState(state: string): Promise<WorkflowInstance[]> {
    const results = this.sql.exec(
      "SELECT * FROM workflow_instances WHERE current_state = ?",
      state
    ).toArray()

    return results.map((row: any) => ({
      id: row.id,
      definition: JSON.parse(row.definition),
      current_state: row.current_state,
      context: JSON.parse(row.context),
      history: JSON.parse(row.history),
      created_at: row.created_at,
      updated_at: row.updated_at,
      expires_at: row.expires_at,
    }))
  }

  // Clean up expired instances
  async cleanup(): Promise<number> {
    const now = new Date().toISOString()
    const result = this.sql.exec(
      "DELETE FROM workflow_instances WHERE expires_at < ?",
      now
    )
    return result.changes || 0
  }

  // Handle HTTP requests from Worker
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url)

    if (request.method === "POST" && url.pathname === "/create") {
      const body = await request.json() as WorkflowInstance
      const result = await this.create(body)
      return Response.json(result)
    }

    if (request.method === "GET" && url.pathname === "/state") {
      const id = url.searchParams.get("id")
      if (!id) return new Response("Missing id", { status: 400 })
      const state = await this.getState(id)
      if (!state) return new Response("Not found", { status: 404 })
      return Response.json(state)
    }

    if (request.method === "POST" && url.pathname === "/transition") {
      const { id, event, newState, context } = await request.json() as any
      const result = await this.transition(id, event, newState, context)
      return Response.json(result)
    }

    return new Response("Not found", { status: 404 })
  }
}
