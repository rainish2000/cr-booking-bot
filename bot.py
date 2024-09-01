import logging
import os
import psycopg2
import boto3
import json
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, ConversationHandler, filters
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_HOSTNAME = os.getenv("DB_HOSTNAME")
PORT = os.getenv("PORT")
SECRET_NAME = os.getenv("SECRET_NAME")
CHAT_ID = os.getenv("CHAT_ID")
THREAD_ID = os.getenv("THREAD_ID")

region_name = "ap-southeast-1"

# Create a Secrets Manager client
session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager',
    region_name=region_name
)

try:
    get_secret_value_response = client.get_secret_value(
        SecretId=SECRET_NAME
    )

except Exception as e:
    raise e

secret = json.loads(get_secret_value_response['SecretString'])

username = secret['username']
password = secret['password']


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def connect_to_db():
    return psycopg2.connect( dbname="postgres", user=username, password=password, host=DB_HOSTNAME, port=PORT, )\
    
with connect_to_db() as conn:
    c = conn.cursor
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
SELECTING_DATE, SELECTING_START, SELECTING_END, TYPING_DETAILS, DELETING_BOOKING = range(5)

# State dictionary to manage user interactions
user_state = {}

# Calendar style
class MyStyleCalendar(DetailedTelegramCalendar):
    prev_button = "<"
    next_button = ">"
    empty_month_button = ""
    empty_year_button = ""

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_type = update.message.chat.type
    # if chat_type == 'private':
    await update.message.reply_text('Hello! Start a private chat with me and use /book to make a new booking, or /list to view upcoming bookings.')
    chat_id = update.message.chat_id
    thread_id = update.message.message_thread_id
    print(f"Chat ID: {chat_id}")
    print(f"Thread ID: {thread_id}")
    print(f"Type: {chat_type}")


async def help_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Use /book to make a booking. Use /list to view upcoming bookings.')

async def book(update: Update, context: CallbackContext) -> int:
    chat_type = update.message.chat.type
    if chat_type == 'supergroup':
            return ConversationHandler.END
    user_id = update.message.from_user.id
    user_state[user_id] = {}

    # Define the minimum and maximum dates for the calendar
    today = date.today()
    min_date = today  # Start from today
    max_date = date(today.year + 1, 12, 31)  # Up to the end of next year

    # Create and display a calendar with a restricted year range
    calendar, step = MyStyleCalendar(min_date=min_date, max_date=max_date).build()
    await update.message.reply_text(f"Select {LSTEP[step]}:", reply_markup=calendar)
    return SELECTING_DATE

async def handle_date_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    today = date.today()
    min_date = today  # Start from today
    max_date = date(today.year + 1, 12, 31)  # Up to the end of next year
    result, key, step = MyStyleCalendar(min_date=min_date, max_date=max_date).process(query.data)

    if not result and key:
        await query.edit_message_text(f"Select {LSTEP[step]}:", reply_markup=key)
    elif result:
        selected_date = result.strftime(DATE_FORMAT)
        user_state[user_id]['date'] = selected_date

        # Fetch booked time slots for the selected date
        with connect_to_db() as conn:
            c = conn.cursor()
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
        #// keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_start")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f'You have chosen {selected_date}. Select a start time:', reply_markup=reply_markup)
        return SELECTING_START

async def handle_start_time_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return ConversationHandler.END

    #//  if query.data == "back_to_start":
    #//     return await handle_date_selection()

    user_id = query.from_user.id
    selected_start_time = query.data.split(':')[1]
    user_state[user_id]['start_time'] = selected_start_time

    selected_date = user_state[user_id]['date']
    start_time = datetime.strptime(selected_start_time, TIME_FORMAT).time()

    # Fetch booked time slots for the selected date
    with connect_to_db() as conn:
        c = conn.cursor
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
    #// keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_start_time")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f'You have chosen start time {selected_start_time}. Select an end time:', reply_markup=reply_markup)
    return SELECTING_END

async def handle_end_time_selection(update: Update, context: CallbackContext) -> int:
    """Handle end time selection and prompt for meeting details."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text('Booking process canceled.')
        return ConversationHandler.END

    #// if query.data == "back_to_start_time":
    #//     print("back to start time pressed")
    #//     return SELECTING_START
    
    user_id = query.from_user.id
    selected_end_time = query.data.split(':')[1]
    user_state[user_id]['end_time'] = selected_end_time

    # Prompt user to enter meeting details
    await query.edit_message_text(f"You have chosen end time {selected_end_time}. Please type in the details for the meeting:\nE.g. \"Meeting with XXX\"")
    return TYPING_DETAILS

async def receive_meeting_details(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    details = update.message.text
    user_state[user_id]['details'] = details

    date = user_state[user_id]['date']
    start_time = user_state[user_id]['start_time']
    end_time = user_state[user_id]['end_time']
    username = update.message.from_user.username

    # Insert the booking into the database
    with connect_to_db() as conn:
        c = conn.cursor
        c.execute('INSERT INTO bookings (date, start_time, end_time, username, details) VALUES (%s, %s, %s, %s, %s)', 
                (date, start_time, end_time, username, details))
        conn.commit()

    await update.message.reply_text(
        f"Conference Room booked for {date} from {start_time} to {end_time} by @{username}.\nDetails: {details}",
        reply_markup=ReplyKeyboardRemove()
    )
    try:
        await context.bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=f"Conference room booked for {date} from {start_time} to {end_time} by @{username}.\nDetails: {details}")
    except:
        print(f"chat {CHAT_ID} not found")

    payload = {
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "details": details,
        "telegram_user": username
    }

    # response = requests.post("https://hooks.slack.com/triggers/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", json=payload)

    user_state.pop(user_id, None)
    return ConversationHandler.END

async def list_bookings(update: Update, context: CallbackContext) -> None:
    """List all upcoming bookings."""
    response = "Upcoming Bookings:\n\n"
    
    # Fetch all bookings from the database
    with connect_to_db() as conn:
        c = conn.cursor
        c.execute('SELECT date, start_time, end_time, username, details FROM bookings')
        rows = c.fetchall()
    #// print(rows)
    
    # Get current date and time
    now = datetime.now()
    
    # List of upcoming bookings
    upcoming_bookings = []
    
    for row in rows:
        booking_date = datetime.strptime(row[0], DATE_FORMAT)
        booking_start_time = datetime.strptime(row[1], TIME_FORMAT).time()
        booking_end_time = datetime.strptime(row[2], TIME_FORMAT).time()
        
        # Check if the booking is upcoming (not yet ended)
        if datetime.combine(booking_date, booking_end_time) > now:
            upcoming_bookings.append((booking_date, booking_start_time, booking_end_time, row[3], row[4]))

    # Sort upcoming bookings by date
    upcoming_bookings.sort(key=lambda x: x[0])
    for booking in upcoming_bookings:
        print(booking)

    # Create the response message
    for booking in upcoming_bookings:
        booking_date_str = booking[0].strftime(DATE_FORMAT)
        booking_start_str = booking[1].strftime(TIME_FORMAT)
        booking_end_str = booking[2].strftime(TIME_FORMAT)
        username = booking[3]
        details = booking[4]
        
        response += f"{booking_date_str} from {booking_start_str} to {booking_end_str} by @{username} - {details} \n\n"

    # If there are no upcoming bookings
    if not upcoming_bookings:
        response = "There are no upcoming bookings."

    await update.message.reply_text(response)

async def delete_booking(update: Update, context: CallbackContext) -> int:
    chat_type = update.message.chat.type
    if chat_type == 'supergroup':
            return ConversationHandler.END
    user = update.message.from_user
    username = user.username

    # Fetch all bookings made by the user
    with connect_to_db() as conn:
        c = conn.cursor
        c.execute("SELECT id, date, start_time, end_time, details FROM bookings WHERE username = %s;", (username,))
        results = c.fetchall()

    if not results:
        await update.message.reply_text('You have no bookings to delete.')
        return ConversationHandler.END

    # Format the list of bookings
    booking_list = ["Your bookings:"]
    for booking in results:
        booking_list.append(f"ID: {booking[0]}, Date: {booking[1]}, Start: {booking[2]}, End: {booking[3]}, Details: {booking[4]}")

    # Send the list of bookings to the user
    await update.message.reply_text("\n".join(booking_list))
    await update.message.reply_text('Please provide the booking ID you want to delete. E.g. if your booking\'s ID shown above is 4, just reply with "4". Type "cancel" to cancel.')

    return DELETING_BOOKING

async def confirm_delete_booking(update: Update, context: CallbackContext) -> int:
    """Delete the booking if the user provides the correct ID."""
    user = update.message.from_user
    username = user.username
    booking_id = update.message.text.strip()

    if booking_id == "cancel":
        await update.message.reply_text('Operation cancelled.')
        return ConversationHandler.END

    # Fetch the booking to verify the user
    with connect_to_db() as conn:
        c = conn.cursor
        try:
            c.execute("SELECT username FROM bookings WHERE id = %s;", (booking_id,))
            result = c.fetchone()
        except:
            await update.message.reply_text('An error occured. Try again using /delete, and please provide only a single number in your reply.')
            c.connection.rollback()
            return ConversationHandler.END

        if result is None:
            await update.message.reply_text('Booking not found with that ID. Operation cancelled.')
            return ConversationHandler.END

        if result[0] != username:
            await update.message.reply_text('You can only delete your own bookings. Operation cancelled.')
            return ConversationHandler.END

        # Delete the booking
        c.execute("DELETE FROM bookings WHERE id = %s;", (booking_id,))
        conn.commit()

    await update.message.reply_text(f'Booking with ID {booking_id} has been deleted.')
    # try:
    #     await context.bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=f'Booking with ID {booking_id} was deleted by @{username}.')
    # except:
    #     print(f"chat {CHAT_ID} not found")

    return ConversationHandler.END
    
async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the conversation."""
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

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

    delete_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', delete_booking)],
        states={
            DELETING_BOOKING: [MessageHandler(filters.TEXT, confirm_delete_booking)],
        },
        fallbacks=[CallbackQueryHandler(delete_booking, pattern="^cancel$")],
    )
    
    application.add_handler(delete_conv_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()