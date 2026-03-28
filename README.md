# Redis Events

A system for managing physical events (workshops, lectures, seminars) in real time. People can find events near them, join them, chat with other participants, and leave when they're done. Admins can create, start, and stop events.

Built with **Python**, **Redis**, and **SQLite**. Developed for the Key-Value Stores course at AUEB.

---

## What Does This App Do?

Imagine a university is hosting several events across campus at the same time. This app lets you:

- **Find events** happening near your location
- **Join** an event (check in)
- **Chat** with other people who joined the same event
- **Leave** the event (check out)
- **See** who else is attending

Admins can also create events, start/stop them manually, and force-add or remove users.

---

## Why Redis?

We could store everything in SQLite alone — so why add Redis?

SQLite writes data to a file on disk. That's great for saving things permanently, but every read and write involves disk access, which is slow. When dozens of users are checking in, chatting, and searching for events at the same time, disk-based lookups become a bottleneck.

Redis stores everything **in memory (RAM)**, which makes it orders of magnitude faster. Looking up whether a user is already checked in, counting participants, or fetching chat messages all happen almost instantly. The tradeoff is that RAM is temporary — if Redis restarts, the data is gone. That's why we keep SQLite as the permanent backup: events are defined in SQLite and only loaded into Redis while they're actively running.

In short: **SQLite = slow but permanent, Redis = fast but temporary**. We use both to get the best of each.

---

## How It Works (The Big Picture)

The app uses **two databases** working together:

1. **SQLite** (a file-based database) stores all events permanently. Even if you restart the app, the events are still there. It also keeps a log of every action (who joined, who left, etc.).

2. **Redis** (an in-memory key-value store) holds only the events that are **currently happening right now**. Since Redis stores everything in RAM, it's extremely fast — perfect for things like checking in, chatting, and counting participants in real time.

A **background timer** runs every 60 seconds and automatically:
- Loads events into Redis when their start time arrives
- Removes events from Redis when their end time passes

So you don't have to manually start and stop events — it happens on its own.

> **Browser** &rarr; **Flask Server (app.py)** &rarr; talks to three things:
>
> 1. **Redis** &mdash; fast, in-memory store for live event data
> 2. **SQLite** &mdash; permanent database that saves events and logs forever
> 3. **Background Timer** &mdash; automatically loads/unloads events every 60 seconds

---

## How Data Is Stored in Redis

Redis doesn't use tables like a normal database. Instead, it uses simple key-value pairs with different data types. Here's what we store:

### Active Events List

A **set** (like a list with no duplicates) that holds the IDs of all events happening right now.

```
Key:   active_events
Value: {"evt-001", "evt-002", "evt-003"}
```

Before doing anything with an event (joining, chatting, etc.), the app checks this set first to make sure the event is actually active.

### Event Details

Each active event has a **hash** (like a dictionary/object) with all its information.

```
Key:   event:evt-001

Fields:
  title       → "Python Workshop"
  subtitle    → "Intro to Flask"
  lat         → "37.9838"          (latitude — where the event is)
  lon         → "23.7275"          (longitude)
  radius      → "500"              (how close you need to be, in meters)
  start_time  → "1711612800"       (when it starts, as a Unix timestamp)
  end_time    → "1711620000"       (when it ends)
  audience    → ""                 (empty = anyone can join)
  special_participants → ""        (VIP emails that always have access)
```

**Public vs Private events:**
- If `audience` is empty → the event is **public**, anyone can join
- If `audience` has emails (like `"student@aueb.gr,prof@aueb.gr"`) → only those people can join

### Participants

A **sorted set** that tracks who has joined an event. Each person's email is stored along with the time they joined.

```
Key:   event:evt-001:participants

Members:
  "user@aueb.gr"   → joined at 1711613045
  "admin@aueb.gr"  → joined at 1711613102
```

This lets us:
- Check if someone already joined (so they can't join twice)
- Count how many people are in the event
- List everyone in the order they joined

### Chat Messages

Another **sorted set** that stores chat messages for each event, ordered by time.

```
Key:   event:evt-001:chat

Members:
  {"email":"user@aueb.gr", "text":"Hello!", "timestamp":1711613200}   → 1711613200
  {"email":"admin@aueb.gr", "text":"Welcome!", "timestamp":1711613250} → 1711613250
```

Only people who have joined the event can send messages.

### What Happens When an Event Ends?

When an event is stopped (manually or by the timer), **all of its Redis data gets deleted**:
- The event details hash
- The participants list
- The chat messages
- Its entry in the active events set

This keeps Redis clean and fast.

---

## How Data Is Stored in SQLite

SQLite has two tables:

### Events Table

Stores all event definitions permanently. This is where events live even when they're not active.

| Column | What it stores |
|--------|---------------|
| event_id | Unique ID like `evt-001` |
| title | Event name |
| subtitle | Short description |
| lat, lon | GPS coordinates of the event location |
| radius | How close (in meters) someone needs to be to "find" this event |
| start_time, end_time | When the event starts and ends (Unix timestamps) |
| special_participants | Emails that always have access (comma-separated) |
| audience | If set, only these emails can join (comma-separated). Empty = public |

### Log Table

Every important action gets logged here for record-keeping.

| Column | What it stores |
|--------|---------------|
| log_id | Auto-generated number |
| timestamp | When the action happened |
| action | What happened (e.g., `checkin`, `checkout`, `stop-event`) |
| event_id | Which event it was about |
| email | Which user did it |
| details | Any extra info |

---

## All API Endpoints

The server exposes these URLs that the frontend (or any client) can call. They all return JSON.

### Setting Up

| Method | URL | What it does |
|--------|-----|-------------|
| POST | `/api/seed` | Creates 3 sample events for testing and loads them into Redis |
| GET | `/api/get-events` | Returns a list of all currently active events with full details |

The seed creates these test events (all centered around Athens):

| ID | Name | Who can join | Radius |
|----|------|-------------|--------|
| evt-001 | Python Workshop | Anyone (admin@aueb.gr is special) | 500m |
| evt-002 | AI Seminar | Only student@aueb.gr and prof@aueb.gr | 300m |
| evt-003 | Math Lecture | Anyone | 1000m |

### Starting and Stopping Events (Admin)

| Method | URL | What it does |
|--------|-----|-------------|
| POST | `/api/start-event` | Loads an event from SQLite into Redis (makes it active) |
| POST | `/api/stop-event` | Removes an event from Redis (deactivates it, deletes participants and chat) |

Both expect: `{ "event_id": "evt-001" }`

### Joining and Leaving Events

| Method | URL | What it does |
|--------|-----|-------------|
| POST | `/api/checkin` | Join an event (checks if you're allowed and not already in) |
| POST | `/api/checkout` | Leave an event |
| POST | `/api/checkin-byadmin` | Admin adds someone to an event (skips audience check) |
| POST | `/api/checkout-byadmin` | Admin removes someone from an event |

All expect: `{ "email": "user@aueb.gr", "event_id": "evt-003" }`

### Finding Events Near You

| Method | URL | What it does |
|--------|-----|-------------|
| GET | `/api/find-events?email=...&x=...&y=...` | Finds events within range of the given GPS coordinates that the user is allowed to access |

The app calculates the distance between your coordinates and each event's location using the **Haversine formula** (the standard way to measure distance on a sphere like Earth). If you're within the event's radius, it shows up in the results.

### Viewing Participants

| Method | URL | What it does |
|--------|-----|-------------|
| GET | `/api/get-participants?event_id=...` | Returns all participants with their join times |
| GET | `/api/num-participants?event_id=...` | Returns just the count |

### Chat

| Method | URL | What it does |
|--------|-----|-------------|
| POST | `/api/post-to-chat` | Send a message (you must be a participant). Expects: `{ "email": "...", "event_id": "...", "text": "..." }` |
| GET | `/api/get-posts?event_id=...` | Get all messages in an event's chat |
| GET | `/api/get-user-posts?email=...` | Get all messages by a specific user across all active events |

---

## The Web Interface

Open `http://localhost:5000` in your browser and you'll see a testing dashboard split into 6 sections:

1. **Setup** — Create test events and view what's currently active
2. **Start / Stop Event** — Manually activate or deactivate events (admin only)
3. **Check-in / Check-out** — Join or leave events
4. **Find Events Nearby** — Search by GPS coordinates
5. **Participants** — See who's in an event
6. **Chat** — Send and read messages

**How to use it:**
- Type your email in the top bar — all actions will use this email
- Toggle the **Admin** switch to show/hide admin-only features
- Every action shows a green (success) or red (error) notification
- The dark box at the top shows the raw JSON response from the server, color-coded for readability

---

## How to Set It Up

### Step 1: Make sure you have Python and Redis

- **Python 3.8 or newer** — Download from [python.org](https://www.python.org/downloads/) if you don't have it
- **Redis** — Download from [redis.io](https://redis.io/download). On Windows, you can use WSL (Windows Subsystem for Linux) or [Memurai](https://www.memurai.com/)

### Step 2: Install the Python libraries

Open a terminal in the project folder and run:

```bash
pip install -r requirements.txt
```

This reads the `requirements.txt` file and installs everything the app needs:
- `flask` — the web framework that runs the server
- `redis` — the Python library to talk to Redis
- `apscheduler` — the library that runs the background timer

### Step 3: Start Redis

Open a **separate terminal** and run:

```bash
redis-server
```

Leave this running. Redis needs to be active for the app to work.

### Step 4: Start the app

In the project folder, run:

```bash
python app.py
```

You should see something like:

```
 * Running on http://127.0.0.1:5000
```

### Step 5: Open it in your browser

Go to `http://localhost:5000`

### Step 6: Try it out

1. Turn on the **Admin** toggle (top right)
2. Click **Create 3 Test Events**
3. Click **Show Active Events** — you should see 3 events appear
4. Type an email like `user@aueb.gr` in the email bar
5. Type `evt-003` in the Check-in section and click **Join Event**
6. Go to the Chat section, type `evt-003`, write a message, and click **Send Message**
7. Click **View All Messages** to see it

---

## Project Files

```
redis_events/
├── app.py              # The entire backend — server, API routes, Redis and SQLite logic
├── requirements.txt    # Python libraries needed to run the app
├── events.db           # SQLite database file (created automatically when you run the app)
├── templates/
│   └── index.html      # The web page
├── static/
│   ├── style.css       # How the page looks (colors, layout, fonts)
│   └── script.js       # How the page behaves (button clicks, API calls, notifications)
└── README.md           # This file
```
