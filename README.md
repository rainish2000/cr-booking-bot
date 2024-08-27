# Conference Room Booking Bot
A simple telegram bot to book a conference room, using python.

Hi all! Wanted to share something I've been working on that I thought might be useful here - @SmartsNSmilesBot 

It's a bot to help book the CR, since I noticed that currently we just do it through the Room Use topic. Although that's simple, it also makes it a little difficult to track the bookings if the chat gets cluttered, and allows people's bookings to clash, requiring deconfliction afterwards. 

I wrote this bot to at least solve these 2 problems - tracking bookings and removing the need for deconfliction.
So here are its main features:
- lets you choose a timeslot to book the CR
- once you have booked a timeslot, nobody else is able to book the slot
- lets you list all upcoming bookings by date, nearest first
- tracks the user that made each booking
- lets you delete your own bookings (in case of typos, misclicks, etc)

Possible features to add in future:
- have the bot send a message to the "room use" topic every time someone books the room (the bot will have to be added to the group for this)
- allow editing of bookings, currently only allows deletion
- allow booking of different rooms, currently defaults to Conference Room

