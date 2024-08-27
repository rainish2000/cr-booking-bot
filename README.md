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
- allow booking of more than one room, currently only allows Conference Room
- allow editing of bookings, currently only allows deletion

If you'd like to and have the time, you can test it out by starting a chat with @SmartsNSmilesBot and hitting "start". Let me know what you guys think, thanks!