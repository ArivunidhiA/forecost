import click

from forecost import __version__
from forecost.commands.burn_cmd import burn
from forecost.commands.calc_cmd import calc
from forecost.commands.calibration_cmd import calibration
from forecost.commands.demo_cmd import demo
from forecost.commands.export_cmd import export_data
from forecost.commands.forecast_cmd import forecast
from forecost.commands.ingest_cmd import ingest
from forecost.commands.init_cmd import init
from forecost.commands.ledger_cmd import ledger
from forecost.commands.optimize_cmd import optimize
from forecost.commands.price_cmd import price
from forecost.commands.purge_cmd import purge
from forecost.commands.reconcile_cmd import reconcile
from forecost.commands.reset_cmd import reset
from forecost.commands.serve_cmd import serve
from forecost.commands.status_cmd import status
from forecost.commands.track_cmd import track
from forecost.commands.watch_cmd import watch


@click.group()
@click.version_option(__version__, "--version", prog_name="forecost")
def main():
    """forecost -- Know exactly what your AI project will cost."""
    pass


main.add_command(calc)
main.add_command(demo)
main.add_command(export_data)
main.add_command(init)
main.add_command(forecast)
main.add_command(optimize)
main.add_command(price)
main.add_command(purge)
main.add_command(reset)
main.add_command(serve)
main.add_command(status)
main.add_command(track)
main.add_command(watch)
main.add_command(ingest)
main.add_command(ledger)
main.add_command(reconcile)
main.add_command(calibration)
main.add_command(burn)
