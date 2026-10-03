import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchLatest, startRun, subscribeRun } from "../api";
import type { DeskEvent } from "../api";

function respond(status: number, body: unknown = {}) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchLatest", () => {
  it("returns null on 404", async () => {
    vi.stubGlobal("fetch", respond(404));
    expect(await fetchLatest()).toBeNull();
  });

  it("returns the report on 200", async () => {
    vi.stubGlobal("fetch", respond(200, { run_id: "r1" }));
    expect((await fetchLatest())?.run_id).toBe("r1");
  });

  it("throws on network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(fetchLatest()).rejects.toThrow();
  });

  it("throws on server error", async () => {
    vi.stubGlobal("fetch", respond(500));
    await expect(fetchLatest()).rejects.toThrow();
  });
});

describe("startRun", () => {
  it("maps 409 to run_active", async () => {
    vi.stubGlobal("fetch", respond(409, { detail: "run_active" }));
    expect(await startRun()).toEqual({ error: "run_active" });
  });

  it("returns the run id on 200", async () => {
    const fetchMock = respond(200, { run_id: "r2" });
    vi.stubGlobal("fetch", fetchMock);
    expect(await startRun()).toEqual({ run_id: "r2" });
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });
});

describe("subscribeRun", () => {
  class FakeEventSource {
    static last: FakeEventSource;
    listeners = new Map<string, (e: unknown) => void>();
    closed = false;
    constructor(public url: string) {
      FakeEventSource.last = this;
    }
    addEventListener(name: string, handler: (e: unknown) => void) {
      this.listeners.set(name, handler);
    }
    close() {
      this.closed = true;
    }
  }

  it("forwards typed events and unsubscribes", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const events: DeskEvent[] = [];
    const unsubscribe = subscribeRun("r3", (e) => events.push(e));
    const source = FakeEventSource.last;
    expect(source.url).toContain("/desk/runs/r3/events");
    source.listeners.get("node_start")!({ data: JSON.stringify({ node: "stats", phase: "start", run_id: "r3" }) });
    source.listeners.get("done")!({ data: JSON.stringify({ run_id: "r3" }) });
    expect(events.map((e) => e.type)).toEqual(["node_start", "done"]);
    expect(events[0].node).toBe("stats");
    expect(source.closed).toBe(true);
    unsubscribe();
  });

  it("reports connection loss as an error event", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const events: DeskEvent[] = [];
    subscribeRun("r4", (e) => events.push(e));
    FakeEventSource.last.listeners.get("error")!({});
    expect(events[0]).toMatchObject({ type: "error", run_id: "r4" });
  });
});
