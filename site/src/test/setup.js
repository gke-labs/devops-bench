import "@testing-library/jest-dom";

// Node 26 ships its own `localStorage` global that stays undefined unless the
// process is started with --localstorage-file, and its mere presence stops jsdom
// from installing the real one. The result is a jsdom window with no Web Storage
// at all, which no browser resembles: `localStorage.getItem(...)` throws a
// TypeError rather than returning null, so anything touching storage fails for a
// reason that has nothing to do with the code under test.
//
// Install a minimal in-memory Storage when the environment lacks one. Tests that
// need to simulate a browser DENYING access (Safari private browsing, blocked
// site data) spy on these methods and throw from them.
if (!globalThis.localStorage) {
    const store = new Map();
    const storage = {
        getItem: key => (store.has(String(key)) ? store.get(String(key)) : null),
        setItem: (key, value) => { store.set(String(key), String(value)); },
        removeItem: key => { store.delete(String(key)); },
        clear: () => { store.clear(); },
        key: index => [...store.keys()][index] ?? null,
        get length() { return store.size; }
    };
    Object.defineProperty(globalThis, "localStorage", {
        value: storage,
        configurable: true,
        writable: true
    });
}
