from telegram.ext import BaseHandler, CommandHandler
from app.handlers.commands import start

HANDLERS: tuple[BaseHandler] = (CommandHandler("start", start),)
