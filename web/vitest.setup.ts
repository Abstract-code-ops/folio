import { beforeEach, vi } from "vitest";

// Minimal localStorage stub so zustand/persist works in the Node test env
// (the browser supplies the real one). Cleared between tests.
const backing = new Map<string, string>();

const storage: Storage = {
  get length() {
    return backing.size;
  },
  clear: () => backing.clear(),
  getItem: (key) => (backing.has(key) ? backing.get(key)! : null),
  key: (index) => Array.from(backing.keys())[index] ?? null,
  removeItem: (key) => {
    backing.delete(key);
  },
  setItem: (key, value) => {
    backing.set(key, String(value));
  },
};

vi.stubGlobal("localStorage", storage);

beforeEach(() => {
  backing.clear();
});
