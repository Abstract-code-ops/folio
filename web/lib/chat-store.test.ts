import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "./chat-store";

describe("chat send flow (store)", () => {
  beforeEach(() => {
    useChatStore.setState({ sessions: {}, activeByBook: {}, pendingSeed: null });
  });

  it("appends streamed tokens to the trailing ai message", () => {
    const store = useChatStore.getState();
    const id = store.createSession("book1");
    store.addMessage(id, { role: "user", text: "hi" });
    store.addMessage(id, {
      role: "ai",
      text: "",
      citations: [],
      notCovered: null,
    });
    useChatStore.getState().appendToken(id, "Hello");
    useChatStore.getState().appendToken(id, " there");

    const s = useChatStore.getState().getSession(id);
    expect(s?.messages).toHaveLength(2);
    const ai = s?.messages[1];
    expect(ai?.role).toBe("ai");
    expect(ai && "text" in ai ? ai.text : null).toBe("Hello there");
  });

  it("activeByBook points at the created session", () => {
    const store = useChatStore.getState();
    const id = store.createSession("book2");
    expect(useChatStore.getState().activeByBook["book2"]).toBe(id);
  });
});
