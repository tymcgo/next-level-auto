/**
 * agent_client.ts — HTTP client for the Python agentic service.
 * 
 * The Python service exposes:
 * - POST /plan    → takes Moment + CustomerContext → returns Plan [{tool, args}]
 * - POST /execute → takes Plan → runs tools → returns results
 * - POST /govern  → checks approval threshold → sends Telegram request if needed
 * 
 * This client is called by the Worker webhook when a Moment needs planning
 * or governance. Simple tool calls (Twilio, Stripe, audit) stay in the Worker.
 */

export interface Moment {
  idempotency_key: string;
  vin: string;
  mileage?: number;
  dtcs?: string[];
  diag?: string;
  parts?: Array<{ part_number: string; description: string; quantity: number; unit_cost_cents: number }>;
  labor_hours?: number;
  labor_rate_cents?: number;
  estimate_total_cents?: number;
  moment_type: string;
  raw?: string;
  subscription_plan?: string;
}

export interface CustomerContext {
  customer_id: string;
  vin: string;
  last_ro_date?: string;
  last_ro_total_cents?: number;
  second_ro_date?: string;
  second_ro_total_cents?: number;
  subscription_plan?: string;
  credits_remaining?: number;
}

export interface PlanStep {
  tool: string;
  args: Record<string, any>;
}

export interface Plan {
  steps: PlanStep[];
}

export interface GovernanceResult {
  needs_approval: boolean;
  estimate_cents: number;
  threshold_cents: number;
  vin: string;
  summary: string;
}

export interface AgentResult {
  status: 'ok' | 'error' | 'needs_approval';
  plan?: Plan;
  governance?: GovernanceResult;
  error?: string;
}

export class AgentClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Get a plan from the Python planner agent.
   */
  async plan(moment: Moment, context: CustomerContext): Promise<Plan> {
    const r = await fetch(`${this.baseUrl}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moment, context }),
    });
    if (!r.ok) throw new Error(`Plan failed: ${r.status} ${await r.text()}`);
    return await r.json();
  }

  /**
   * Execute a plan via the Python executor.
   * The executor calls back to the Worker's /tool endpoint for each step.
   */
  async execute(plan: Plan, env: Record<string, string>): Promise<any> {
    const r = await fetch(`${this.baseUrl}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan, env }),
    });
    if (!r.ok) throw new Error(`Execute failed: ${r.status} ${await r.text()}`);
    return await r.json();
  }

  /**
   * Check governance: does this moment require owner approval?
   */
  async govern(moment: Moment, thresholdCents: number): Promise<GovernanceResult> {
    const r = await fetch(`${this.baseUrl}/govern`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moment, threshold_cents: thresholdCents }),
    });
    if (!r.ok) throw new Error(`Govern failed: ${r.status} ${await r.text()}`);
    return await r.json();
  }

  /**
   * Full pipeline: plan → govern → return structured result.
   * The Worker decides whether to execute or request approval.
   */
  async processMoment(
    moment: Moment,
    context: CustomerContext,
    thresholdCents: number,
  ): Promise<AgentResult> {
    // 1. Get plan
    const plan = await this.plan(moment, context);

    // 2. Check governance
    const governance = await this.govern(moment, thresholdCents);

    if (governance.needs_approval) {
      return { status: 'needs_approval', plan, governance };
    }

    return { status: 'ok', plan, governance };
  }
}
