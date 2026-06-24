import re

from playwright.async_api import Page
from rich.console import Console

console = Console()

_WATCH_SUFFIX = re.compile(
    r'\s*[\|\-–—]?\s*(watch|streaming?|online|free|hd|4k|full\s*movie|vf|vostfr|sous[- ]titres?).*$',
    re.IGNORECASE,
)
_SITE_SUFFIX = re.compile(r'\s*[\|\-–—]\s*.{3,50}$')
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r'\s+')
_MULTI_DASH = re.compile(r'-{2,}')


class TitleScraperService:
    async def scrape_candidates(self, page: Page) -> list[str]:
        raw: list[str] = await page.evaluate("""() => {
            const out = [];

            if (document.title) out.push(document.title);

            const og = document.querySelector('meta[property="og:title"]');
            if (og?.content) out.push(og.content);

            const tw = document.querySelector('meta[name="twitter:title"]');
            if (tw?.content) out.push(tw.content);

            document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                try {
                    const push = d => { if (d?.name) out.push(d.name); };
                    const d = JSON.parse(s.textContent);
                    push(d);
                    (d['@graph'] || []).forEach(push);
                } catch {}
            });

            document.querySelectorAll('h1').forEach(el => {
                const t = el.textContent.trim();
                if (t) out.push(t);
            });

            const selectors = [
                '[class*="title"]', '[class*="movie-name"]',
                '[class*="film-title"]', '[class*="show-title"]',
                '[itemprop="name"]',
            ];
            document.querySelectorAll(selectors.join(',')).forEach(el => {
                const t = el.textContent.trim();
                if (t && t.length < 120) out.push(t);
            });

            return out;
        }""") or []

        return self._dedupe(raw)

    def to_filename(self, title: str) -> str:
        name = _INVALID_CHARS.sub("", title)
        name = _MULTI_SPACE.sub("-", name.strip())
        name = name.lower().strip("-")
        name = _MULTI_DASH.sub("-", name)
        return name or "video"

    def prompt_user(self, candidates: list[str]) -> str:
        console.print("\n[bold]Detected title suggestions:[/bold]")
        for i, title in enumerate(candidates, 1):
            console.print(f"  [cyan][{i}][/cyan] {title}  [dim]→ {self.to_filename(title)}.mp4[/dim]")
        console.print("  [cyan][0][/cyan] Enter a custom name\n")

        while True:
            raw = input(
                "Pick a number (Enter = use [1]): "
                if candidates
                else "Enter output name: "
            ).strip()

            if not raw and candidates:
                chosen = self.to_filename(candidates[0])
                console.print(f"[dim]Using:[/dim] {chosen}.mp4")
                return chosen

            if raw.isdigit():
                idx = int(raw)
                if idx == 0:
                    custom = input("Custom name: ").strip()
                    if custom:
                        return self.to_filename(custom)
                elif 1 <= idx <= len(candidates):
                    return self.to_filename(candidates[idx - 1])
            elif raw:
                return self.to_filename(raw)

            console.print("[yellow]Invalid choice, try again.[/yellow]")

    # ── private ───────────────────────────────────────────────────────────────

    def _dedupe(self, raw: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for title in raw:
            title = _MULTI_SPACE.sub(" ", title).strip()
            title = _WATCH_SUFFIX.sub("", title).strip()
            title = _SITE_SUFFIX.sub("", title).strip(" -|–—")
            if not title or len(title) < 2 or len(title) > 100:
                continue
            key = title.lower()
            if key not in seen:
                seen.add(key)
                out.append(title)
        return out
