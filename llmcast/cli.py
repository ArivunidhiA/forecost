import click

from llmcast.commands.demo_cmd import demo
from llmcast.commands.export_cmd import export_data
from llmcast.commands.forecast_cmd import forecast
from llmcast.commands.init_cmd import init
from llmcast.commands.optimize_cmd import optimize
from llmcast.commands.reset_cmd import reset
from llmcast.commands.serve_cmd import serve
from llmcast.commands.status_cmd import status
from llmcast.commands.track_cmd import track
from llmcast.commands.watch_cmd import watch


@click.group()
@click.version_option(package_name="llmcast")
def main():
    """llmcast -- Know exactly what your AI project will cost."""
    pass


main.add_command(demo)
main.add_command(export_data)
main.add_command(init)
main.add_command(forecast)
main.add_command(optimize)
main.add_command(reset)
main.add_command(serve)
main.add_command(status)
main.add_command(track)
main.add_command(watch)
