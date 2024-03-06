Python script to create car pools for travelers

## Input
### input/event.txt
File containing information about the event and travelers in the following format

```
Players
-------------
<Player Name>:<Seats Taken>:<Post Code>:<Is Driver - true|false>:<Group ID or 0>:<Must Drive - true|false>
<Player Name>:<Seats Taken>:<Post Code>:<Is Driver - true|false>:<Group ID or 0>:<Must Drive - true|false>
<Player Name>:<Seats Taken>:<Post Code>:<Is Driver - true|false>:<Group ID or 0>:<Must Drive - true|false>
<Player Name>:<Seats Taken>:<Post Code>:<Is Driver - true|false>:<Group ID or 0>:<Must Drive - true|false>
<Player Name>:<Seats Taken>:<Post Code>:<Is Driver - true|false>:<Group ID or 0>:<Must Drive - true|false>

Details
--------------
Event Address:<Event Post Code>
Start Time: <ISO 8601 Time of the Event e.g. 2024-03-09 13:00:00.000>
```
### input/google_token.txt
File containing the Google Maps API token for distance calculations in the following format
```
<Google Maps API Token>
```


