try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import DataTable, Footer, Header, Static

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False

if HAS_TEXTUAL:
    try:
        import plotext as plt

        HAS_PLOTEXT = True
    except ImportError:
        HAS_PLOTEXT = False


def _text_bar_chart(daily_costs: list[tuple[str, float]], width: int = 40) -> str:
    if not daily_costs:
        return "No daily data yet"
    max_cost = max(c for _, c in daily_costs)
    if max_cost <= 0:
        return "No costs recorded"
    lines = []
    for day, cost in daily_costs[-14:]:
        bar_len = int((cost / max_cost) * width) if max_cost > 0 else 0
        bar = "█" * bar_len
        lines.append(f"{day[:10]:<12} {bar} ${cost:.2f}")
    return "\n".join(lines)


def _plotext_bar_chart(daily_costs: list[tuple[str, float]]) -> str:
    if not daily_costs or not HAS_PLOTEXT:
        return _text_bar_chart(daily_costs)
    try:
        plt.clf()
        costs = [c for _, c in daily_costs[-14:]]
        if not costs:
            return _text_bar_chart(daily_costs)
        plt.simple_bar(range(len(costs)), costs, width=0.5)
        plt.xlabel("Day")
        plt.ylabel("Cost ($)")
        return plt.build()
    except Exception:
        return _text_bar_chart(daily_costs)


if HAS_TEXTUAL:

    class ForecastDashboard(App):
        TITLE = "forecost -- Cost Forecast Dashboard"
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh", "Refresh"),
        ]
        CSS = """
        .left-panel { width: 60%; }
        .right-panel { width: 40%; }
        """

        def __init__(self, forecast_result: dict, project_id: int, on_refresh=None):
            super().__init__()
            self._forecast = forecast_result
            self._project_id = project_id
            self._on_refresh = on_refresh

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Horizontal():
                with Vertical(classes="left-panel"):
                    yield Static("", id="projected-total")
                    yield Static("", id="daily-chart")
                with Vertical(classes="right-panel"):
                    yield Static("", id="stats-panel")
                    yield Static("Model breakdown", id="model-table-label")
                    yield DataTable(id="model-table")
                    yield Static("Forecast history", id="history-label")
                    yield DataTable(id="history-table")
            yield Footer()

        def on_mount(self) -> None:
            self._populate()

        def _populate(self) -> None:
            f = self._forecast
            total = f.get("projected_total", 0)
            self.query_one("#projected-total", Static).update(
                f"[bold cyan]Projected Total:[/] [bold green]${total:.2f}[/]"
            )

            from forecost.db import get_daily_costs, get_forecast_history

            daily_costs = get_daily_costs(self._project_id)
            chart_content = (
                _plotext_bar_chart(daily_costs) if HAS_PLOTEXT else _text_bar_chart(daily_costs)
            )
            self.query_one("#daily-chart", Static).update(chart_content)

            actual = f.get("actual_spend", 0)
            remaining = f.get("projected_remaining", 0)
            burn = f.get("smoothed_burn_ratio", 0)
            conf = f.get("confidence", "—")
            drift = f.get("drift_status", "—")
            stats = (
                f"Actual Spend: ${actual:.2f}\n"
                f"Remaining: ${remaining:.2f}\n"
                f"Burn Ratio: {burn:.2f}x\n"
                f"Confidence: {conf}\n"
                f"Drift: {drift}"
            )
            self.query_one("#stats-panel", Static).update(stats)

            model_table = self.query_one("#model-table", DataTable)
            model_table.clear()
            model_table.add_columns("Model", "Spent", "Projected", "Share")
            for m in f.get("model_breakdown", []):
                model_table.add_row(
                    m.get("model", ""),
                    f"${m.get('spent', 0):.2f}",
                    f"${m.get('projected', 0):.2f}",
                    f"{m.get('share', 0) * 100:.1f}%",
                )

            history = get_forecast_history(self._project_id)
            hist_table = self.query_one("#history-table", DataTable)
            hist_table.clear()
            hist_table.add_columns("Iter", "Projected Total")
            for h in history[-10:]:
                hist_table.add_row(
                    str(h.get("iteration", "")),
                    f"${h.get('projected_total', 0):.2f}",
                )

        def action_refresh(self) -> None:
            if self._on_refresh:
                self._forecast = self._on_refresh()
                self._populate()

        def action_quit(self) -> None:
            self.exit()


def launch(forecast_result: dict, project_id: int, on_refresh=None):
    if not HAS_TEXTUAL:
        print("TUI requires Textual. Install with: pip install forecost[tui]")
        return
    app = ForecastDashboard(forecast_result, project_id, on_refresh)
    app.run()
