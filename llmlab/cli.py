import click

from llmlab.commands.forecast_cmd import forecast
from llmlab.commands.init_cmd import init
from llmlab.commands.serve_cmd import serve
from llmlab.commands.status_cmd import status
from llmlab.commands.track_cmd import track


@click.group()
@click.version_option(package_name="llmlab")
def main():
    """llmlab -- Know exactly what your AI project will cost."""
    pass


main.add_command(init)
main.add_command(forecast)
main.add_command(status)
main.add_command(track)
main.add_command(serve)
