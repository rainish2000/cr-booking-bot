import logging
import os
import psycopg2
import telegram_bot_calendar
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, ConversationHandler, filters
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telegram_bot_calendar import DetailedTelegramCalendar

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize PostgreSQL database
conn = psycopg2.connect(DATABASE_URL)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id SERIAL PRIMARY KEY,
        date TEXT,
        start_time TEXT,
        end_time TEXT,
        username TEXT,
        details TEXT
    );
''')
conn.commit()

# Date format
DATE_FORMAT = "%d %b %Y"
TIME_FORMAT = "%H%M"
SELECTING_DATE, SELECTING_START, SELECTING_END, TYPING_DETAILS = range(4)

# State dictionary to manage user interactions
user_state = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_markdown_v2(
        fr'Hi {user.mention_markdown_v2()}\! Use /book to make a booking, or /list to view upcoming bookings',
    )

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text('Use /book to book the conference room. Use /list to view all bookings.')

async def book(update: Update, context: CallbackContext) -> int:
    """Handle the /book command by showing a calendar to select a date."""
    user_id = update.message.from_user.id
    user_state[user_id] = {}

    # Create and display a calendar
    calendar, step = DetailedTelegramCalendar().build()
    await update.message.reply_text(f"Select {step}:", reply_markup=calendar)
    return SELECTING_DATE

async def handle_date_selection(update: Update, context: CallbackContext) -> int:
    """Handle date selection from the calendar."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    result, key, step = DetailedTelegramCalendar().process(query.data)

    if not result and key:
        await query.edit_message_text(f"Select {step}:", reply_markup=key)
    elif result:
        selected_date = result.strftime("%d-%m-%Y")
        user_state[user_id]['date'] = selected_date

        # Fetch booked time slots for the selected date
        c.execute('SELECT start_time, end_time FROM bookings WHERE date = %s', (selected_date,))
        booked_slots = c.fetchall()

        # Convert booked slots to datetime.time objects
        booked_slots = [(datetime.strptime(start, TIME_FORMAT).time(), datetime.strptime(end, TIME_FORMAT).time()) for start, end in booked_slots]

        # Generate available start time slots (on the hour from 09:00 to 17:00)
        start_hour = 9
        end_hour = 17
        time_slots = []
        for hour in range(start_hour, end_hour + 1):
            current_time = datetime.strptime(f"{hour:02d}00", TIME_FORMAT).time()
            next_time = (datetime.combine(datetime.today(), current_time) + timedelta(hours=1)).time()
            is_available = all(
                not (start <= current_time < end or
                     start < next_time <= end or
                     current_time <= start < next_time)
                for start, end in booked_slots
            )
            if is_available:
                time_slots.append(current_time.strftime(TIME_FORMAT))

        # Generate time slot buttons
        keyboard = [[InlineKeyboardButton(slot, callback_data=f"start_time:{slot}")] for slot in time_slots]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f'You have chosen {selected_date}. Select a start time:', reply_markup=reply_markup)
        return SELECTING_START

async def handle_start_time_selection(update: Update, context: CallbackContext) -> int:
    """Handle start time selection and show available end times."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return ConversationHandler.END

    user_id = query.from_user.id
    selected_start_time = query.data.split(':')[1]
    user_state[user_id]['start_time'] = selected_start_time

    selected_date = user_state[user_id]['date']
    start_time = datetime.strptime(selected_start_time, TIME_FORMAT).time()

    # Fetch booked time slots for the selected date
    c.execute('SELECT start_time, end_time FROM bookings WHERE date = %s', (selected_date,))
    booked_slots = c.fetchall()

    # Convert booked slots to datetime.time objects
    booked_slots = [(datetime.strptime(start, TIME_FORMAT).time(), datetime.strptime(end, TIME_FORMAT).time()) for start, end in booked_slots]

    # Find the next booking start time after the selected start time
    next_booking_start = None
    for booked_start, _ in booked_slots:
        if booked_start > start_time:
            next_booking_start = booked_start
            break

    # Generate available end time slots (on the hour from start time to the next booking or 18:00)
    end_hour = 18
    if next_booking_start is not None:
        end_hour = min(end_hour, next_booking_start.hour)

    time_slots = []
    current_time = (datetime.combine(datetime.today(), start_time) + timedelta(hours=1)).time()  # Start from the next hour

    while current_time <= datetime.strptime(f"{end_hour:02d}00", TIME_FORMAT).time():
        # Ensure end time does not extend into the next booking slot
        if next_booking_start and current_time > next_booking_start:
            break

        is_available = all(
            not (start < current_time < end)
            for start, end in booked_slots
        )
        if is_available:
            time_slots.append(current_time.strftime(TIME_FORMAT))

        current_time = (datetime.combine(datetime.today(), current_time) + timedelta(hours=1)).time()

    # Include the next booking's start time as an available end time if present
    if next_booking_start and next_booking_start.strftime(TIME_FORMAT) not in time_slots:
        time_slots.append(next_booking_start.strftime(TIME_FORMAT))

    # Generate time slot buttons
    keyboard = [[InlineKeyboardButton(slot, callback_data=f"end_time:{slot}")] for slot in time_slots]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f'You have chosen start time {selected_start_time}. Select an end time:', reply_markup=reply_markup)
    return SELECTING_END

# The rest of the handlers remain unchanged

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_bookings))
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("book", book)],
        states={
            SELECTING_DATE: [CallbackQueryHandler(handle_date_selection)],
            SELECTING_START: [CallbackQueryHandler(handle_start_time_selection)],
            SELECTING_END: [CallbackQueryHandler(handle_end_time_selection)],
            TYPING_DETAILS: [MessageHandler(filters.TEXT, receive_meeting_details)],
        },
        fallbacks=[
            CallbackQueryHandler(handle_date_selection, pattern="^cancel$"),
            CallbackQueryHandler(handle_start_time_selection, pattern="^cancel$"),
            CallbackQueryHandler(handle_end_time_selection, pattern="^cancel$"),
        ],
    )

    # Add the conversation handler to the application
    application.add_handler(conv_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()