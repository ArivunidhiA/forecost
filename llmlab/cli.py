import click

from llmlab.commands.demo_cmd import demo
from llmlab.commands.forecast_cmd import forecast
from llmlab.commands.init_cmd import init
from llmlab.commands.optimize_cmd import optimize
from llmlab.commands.reset_cmd import reset
from llmlab.commands.serve_cmd import serve
from llmlab.commands.status_cmd import status
from llmlab.commands.track_cmd import track
from llmlab.commands.watch_cmd import watch


@click.group()
@click.version_option(package_name="llmlab")
def main():
    """llmlab -- Know exactly what your AI project will cost."""
    pass


main.add_command(demo)
main.add_command(init)
main.add_command(forecast)
main.add_command(optimize)
main.add_command(reset)
main.add_command(serve)
main.add_command(status)
main.add_command(track)
main.add_command(watch)
