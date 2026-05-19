# Conference Room Booking Bot
A simple telegram bot to book a conference room, using python.

I wrote this bot to at least solve these 2 problems - tracking bookings and removing the need for deconfliction.
So here are its main features:
- lets you choose a timeslot to book the CR
- once you have booked a timeslot, nobody else is able to book the slot
- lets you list all upcoming bookings by date, nearest first
- tracks the user that made each booking
- lets you delete your own bookings (in case of typos, misclicks, etc)

- have the bot send a message to the Room Use topic every time someone books the room (the bot will have to be added to the group for this)

## Setup
1. Ensure you have python installed
2. Fork this repository, and `git clone` that repo
3. Follow the steps [here](https://core.telegram.org/bots/tutorial) to obtain the BOT_TOKEN
4. Copy .env.sample, and rename it to .env
5. Update the BOT_TOKEN with your new token from 1
6. The other .env values needed are as follows:
- DB_HOSTNAME	Database server hostname/IP address. Used to connect to the PostgreSQL database
- PORT	Database port number (typically 5432 for PostgreSQL). Used in the connection string to the database
- SECRET_NAME	AWS Secrets Manager secret identifier. Used in production to securely retrieve database credentials (username and password) from AWS
- CHAT_ID	Telegram group chat ID. Used to send booking notifications to a specific Telegram group when bookings are made or deleted
- THREAD_ID	Telegram topic/thread ID within the group chat. Used to post booking notifications to a specific thread within the group
- ENV	Environment flag ("prod" or "dev"). Determines credential handling: in production, credentials are fetched from AWS Secrets Manager; in development, hardcoded credentials are used. Please use "dev" for local testing, as "prod" requires hosting in AWS

7. In terminal, run `pip install -r requirements.txt` at the project root
8. Run `python bot.py` to run the bot locally and access it via Telegram (using the handle you gave it when setting up in step 3)

## Future Improvements
- allow booking of more than one room, currently only allows Conference Room
- allow editing of bookings, currently only allows deletion
