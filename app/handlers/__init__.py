from telegram.ext import BaseHandler, CommandHandler
from app.handlers.commands import start, calendar_command

HANDLERS: tuple[BaseHandler] = (
    CommandHandler("start", start),
    CommandHandler("calendar", calendar_command)
)
