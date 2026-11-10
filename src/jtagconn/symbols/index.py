from __future__ import annotations

from jtagconn.core.models import Symbol


class SymbolIndex:
    """Fast case-insensitive prefix and substring search over symbols."""

    def __init__(self, symbols: list[Symbol] | None = None) -> None:
        self._symbols: list[Symbol] = list(symbols or [])
        self._by_name: dict[str, Symbol] = {s.name: s for s in self._symbols}

    def set_symbols(self, symbols: list[Symbol]) -> None:
        self._symbols = list(symbols)
        self._by_name = {s.name: s for s in self._symbols}

    def add(self, symbol: Symbol) -> None:
        self._symbols.append(symbol)
        self._by_name[symbol.name] = symbol

    def get(self, name: str) -> Symbol | None:
        sym = self._by_name.get(name)
        if sym is not None:
            return sym
        # case-insensitive fallback
        lname = name.lower()
        for s in self._symbols:
            if s.name.lower() == lname:
                return s
        return None

    def search(self, query: str, limit: int = 50) -> list[Symbol]:
        q = query.strip()
        if q == "":
            return sorted(self._symbols, key=lambda s: s.name)[: max(0, int(limit))]
        ql = q.lower()
        prefix_matches: list[Symbol] = []
        substring_matches: list[Symbol] = []
        seen: set[str] = set()
        for sym in self._symbols:
            nl = sym.name.lower()
            if nl.startswith(ql):
                prefix_matches.append(sym)
                seen.add(sym.name)
        for sym in self._symbols:
            if sym.name in seen:
                continue
            if ql in sym.name.lower():
                substring_matches.append(sym)
        prefix_matches.sort(key=lambda s: s.name.lower())
        substring_matches.sort(key=lambda s: s.name.lower())
        result = prefix_matches + substring_matches
        if limit is not None and limit >= 0:
            return result[:limit]
        return result

    def __len__(self) -> int:
        return len(self._symbols)
