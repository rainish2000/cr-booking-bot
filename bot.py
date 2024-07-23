import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize SQLite database
conn = sqlite3.connect('bookings.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        date TEXT,
        start_time TEXT,
        end_time TEXT,
        username TEXT
    )
''')
conn.commit()

# Date format
DATE_FORMAT = "%d-%m-%Y"
TIME_FORMAT = "%H%M"

# State dictionary to manage user interactions
user_state = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_markdown_v2(
        fr'Hi {user.mention_markdown_v2()}\!',
    )

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text('Use /book to book the conference room.')

async def book(update: Update, context: CallbackContext) -> None:
    """Handle the /book command by showing date selection."""
    user_id = update.message.from_user.id
    user_state[user_id] = {}

    # Generate date buttons
    keyboard = []
    today = datetime.now().date()
    for i in range(7):  # Next 7 days
        day = today + timedelta(days=i)
        keyboard.append([InlineKeyboardButton(day.strftime(DATE_FORMAT), callback_data=f"date:{day.strftime(DATE_FORMAT)}")])
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Select a date:', reply_markup=reply_markup)

async def handle_date_selection(update: Update, context: CallbackContext) -> None:
    """Handle date selection and show available start times."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return
    
    user_id = query.from_user.id
    selected_date = query.data.split(':')[1]
    user_state[user_id]['date'] = selected_date

    # Fetch booked time slots for the selected date
    c.execute('SELECT start_time, end_time FROM bookings WHERE date = ?', (selected_date,))
    booked_slots = c.fetchall()

    # Convert booked slots to datetime.time objects
    booked_slots = [(datetime.strptime(start, "%H:%M").time(), datetime.strptime(end, "%H:%M").time()) for start, end in booked_slots]

    # Generate available start time slots (on the hour from 09:00 to 17:00)
    start_hour = 9
    end_hour = 17
    time_slots = []
    for hour in range(start_hour, end_hour + 1):
        current_time = datetime.strptime(f"{hour:02d}00", TIME_FORMAT).time()
        is_available = all(not (start <= current_time < end) for start, end in booked_slots)
        
        if is_available:
            time_slots.append(current_time.strftime(TIME_FORMAT))
    
    # Generate time slot buttons
    keyboard = [[InlineKeyboardButton(slot, callback_data=f"start_time:{slot}")] for slot in time_slots]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f'You have chosen {selected_date}. Select a start time:', reply_markup=reply_markup)

async def handle_start_time_selection(update: Update, context: CallbackContext) -> None:
    """Handle start time selection and show available end times."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return
    
    user_id = query.from_user.id
    selected_start_time = query.data.split(':')[1]
    user_state[user_id]['start_time'] = selected_start_time

    selected_date = user_state[user_id]['date']
    start_time = datetime.strptime(selected_start_time, TIME_FORMAT).time()

    # Fetch booked time slots for the selected date
    c.execute('SELECT start_time, end_time FROM bookings WHERE date = ?', (selected_date,))
    booked_slots = c.fetchall()

    # Convert booked slots to datetime.time objects
    booked_slots = [(datetime.strptime(start, TIME_FORMAT).time(), datetime.strptime(end, TIME_FORMAT).time()) for start, end in booked_slots]

    # Generate available end time slots (on the hour from start time to 18:00)
    end_hour = 18
    time_slots = []
    current_time = (datetime.combine(datetime.today(), start_time) + timedelta(hours=1)).time()  # Start from the next hour
    while current_time <= datetime.strptime(f"{end_hour:02d}00", TIME_FORMAT).time():
        is_available = all(not (start <= current_time < end or current_time < start < (datetime.combine(datetime.today(), current_time) + timedelta(hours=1)).time())
                           for start, end in booked_slots)
        
        if is_available:
            time_slots.append(current_time.strftime(TIME_FORMAT))
        
        current_time = (datetime.combine(datetime.today(), current_time) + timedelta(hours=1)).time()
    
    # Generate time slot buttons
    keyboard = [[InlineKeyboardButton(slot, callback_data=f"end_time:{slot}")] for slot in time_slots]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f'You have chosen start time {selected_start_time}. Select an end time:', reply_markup=reply_markup)

async def handle_end_time_selection(update: Update, context: CallbackContext) -> None:
    """Handle end time selection and confirm the booking."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return
    
    user_id = query.from_user.id
    selected_end_time = query.data.split(':')[1]
    user_state[user_id]['end_time'] = selected_end_time

    date = user_state[user_id]['date']
    start_time = user_state[user_id]['start_time']
    end_time = user_state[user_id]['end_time']
    username = query.from_user.username

    # Insert the booking into the database
    c.execute('INSERT INTO bookings (date, start_time, end_time, username) VALUES (?, ?, ?, ?)', 
              (date, start_time, end_time, username))
    conn.commit()

    await query.edit_message_text(f"Conference room booked for {date} from {start_time} to {end_time} by {username}")

async def list_bookings(update: Update, context: CallbackContext) -> None:
    """List all bookings."""
    response = "Bookings:\n"
    for row in c.execute('SELECT date, start_time, end_time, username FROM bookings'):
        response += f"{row[0]} from {row[1]} to {row[2]} by {row[3]}\n"
    await update.message.reply_text(response)

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("book", book))
    application.add_handler(CommandHandler("list", list_bookings))
    
    # Callback handlers for inline buttons
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern="^date:"))
    application.add_handler(CallbackQueryHandler(handle_start_time_selection, pattern="^start_time:"))
    application.add_handler(CallbackQueryHandler(handle_end_time_selection, pattern="^end_time:"))
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern="^cancel$"))
    application.add_handler(CallbackQueryHandler(handle_start_time_selection, pattern="^cancel$"))
    application.add_handler(CallbackQueryHandler(handle_end_time_selection, pattern="^cancel$"))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()