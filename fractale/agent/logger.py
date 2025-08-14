import sys

from rich import print
from rich.panel import Panel


def success(message, title="Success", border_style="green", expand=True):
    """
    Helper function to print successful message.
    """
    print(
        Panel(
            f"[bold green]✅ {message}[/bold green]",
            title=title,
            border_style=border_style,
            expand=expand,
        )
    )


def error(message, title="Error", border_style="red", expand=True):
    """
    Helper function to print error "beep boop" message.
    """
    print(
        Panel(
            f"[bold red]❌ {message}[/bold red]",
            title=title,
            border_style=border_style,
            expand=expand,
        )
    )


def exit(message, title="Error", border_style="red", expand=True):
    error(message, title, border_style, expand)
    sys.exit(-1)


def warning(message, title="Warning", border_style="yellow"):
    """
    Helper function to print a warning
    """
    print(
        Panel(
            message,
            title=f"[yellow]{title}[/yellow]",
            border_style=border_style,
        )
    )


def custom(message, title, border_style=None, expand=True):
    """
    Custom message / title Panel.
    """
    if not border_style:
        print(Panel(message, title=title, expand=expand))
    else:
        print(Panel(message, title=title, border_style=border_style, expand=expand))


def info(message):
    print(f"\n[bold cyan] {message}[/bold cyan]")
