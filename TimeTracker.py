import duckdb
import pandas as pd
from datetime import datetime, timedelta
from pynput import keyboard
from threading import Thread
import os
import readline

class TimeTracker:
    def __init__(self, db_file='time_tracker.db'):
        os.system('cls' if os.name == 'nt' else 'clear')

        print(" ▗▄▄▖▗▖ ▗▖▗▄▄▖  ▗▄▖ ▗▖  ▗▖ ▗▄▖  ▗▄▄▖")
        print("▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▛▚▖▐▌▐▌ ▐▌▐▌   ")
        print("▐▌   ▐▛▀▜▌▐▛▀▚▖▐▌ ▐▌▐▌ ▝▜▌▐▌ ▐▌ ▝▀▚▖")
        print("▝▚▄▄▖▐▌ ▐▌▐▌ ▐▌▝▚▄▞▘▐▌  ▐▌▝▚▄▞▘▗▄▄▞▘\n")

        self.histfile = os.path.expanduser("~") + "/.input_history"

        if not os.path.exists(self.histfile):
            open(self.histfile, 'w').close()

        try:
            readline.read_history_file(self.histfile)
        except FileNotFoundError:
            pass

        self.hotkeys = keyboard.GlobalHotKeys({'<ctrl>+<alt>+t': self.focus_terminal})
        listener_thread = Thread(target=self.listen_shortcut, daemon=True)
        listener_thread.start()
        self.last_insert_id = None
        self.conn = duckdb.connect(db_file)
        self.init_db()

        self.main()

    def init_db(self):
        self.conn.execute('''CREATE SEQUENCE IF NOT EXISTS seq;''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS time_log (
                id INTEGER DEFAULT nextval('seq'),
                date TEXT,
                time_start TEXT,
                time_end TEXT,
                label TEXT,
                task_id TEXT,
                exported BOOLEAN DEFAULT FALSE
            )
        ''')
        self.conn.execute('''
        CREATE TABLE IF NOT EXISTS drink_log (
            date TEXT,
            drink TEXT,
            quantity INTEGER,
            UNIQUE(date, drink)
        )''')

    def close_current_log(self, base_datetime = None):
        if not self.last_insert_id:
            return
        if base_datetime is None:
            base_datetime = datetime.now()
        time = base_datetime.strftime('%H:%M')
        update_query = """
                    UPDATE time_log
                    SET time_end = ?
                    WHERE id = ?
                """
        self.conn.execute(update_query, (time, self.last_insert_id))
        self.conn.commit()
        self.last_insert_id = None

    def insert_log(self, base_datetime, label):
        self.close_current_log(base_datetime)
        date = base_datetime.strftime('%Y-%m-%d')
        time = base_datetime.strftime('%H:%M')

        result = self.conn.execute("INSERT INTO time_log (date,time_start, label) VALUES (?, ?, ?)  RETURNING (id)",
                          (date, time, label)).fetchone()
        print('You\033[92m started\033[0m working on "' + label + '" at ' + time)
        if result:
            self.last_insert_id = result[0]

    def listen_shortcut(self):
        self.hotkeys.start()

    def focus_terminal(self):
        #os.system('''osascript -e 'tell application "Terminal" to activate' ''')  # Pour Terminal.app
        os.system('''osascript -e 'tell application "iTerm" to activate' ''')  # Si tu utilises iTerm2

    def show_today_summary(self):
        today = datetime.today().strftime('%Y-%m-%d')

        query = f"""
            SELECT id, date,time_start, time_end, label, task_id
            FROM time_log
            WHERE date = '{today}'
        """
        df = self.conn.query(query).df()

        print(df)

    def refresh_duckdb(self):
        query = """DROP TABLE IF EXISTS time_log"""
        self.conn.query(query)
        self.conn.execute("""DROP SEQUENCE IF EXISTS seq""")
        print("Table cleared.")
        self.init_db()

    def end_day(self):
        self.close_current_log()
        today = datetime.today().strftime('%Y-%m-%d')
        logs = self.conn.execute(f"""
            SELECT date,time_start, time_end, label, id
            FROM time_log
            WHERE date = '{today}'
            AND task_id IS NULL
        """).fetchall()

        for log in logs:
            task_id = None
            previous_task = self.conn.execute("""
                                              SELECT task_id 
                                              FROM time_log
                                              WHERE  label = ?
                                              AND task_id IS NOT NULL""", (log[3],)).fetchone()
            if previous_task is not None:
                previous_task_id = previous_task[0]
                reuse = input(f"\"{log[0]} [{log[1]} - {log[2]}] {log[3]}\". Do you want to reuse this log: {previous_task_id}? (y/n): ").strip().lower()
                if reuse == 'y':
                    task_id = previous_task_id

            while not task_id:
                task_id = input(f"Enter task id for \"{log[0]} [{log[1]} - {log[2]}] {log[3]}\": ")
            self.conn.execute("""
                        UPDATE time_log
                        SET task_id = ?
                        WHERE id = ?
                    """, (task_id, log[4]))
            self.conn.commit()

    def log_drink(self, drink):
        today = datetime.today().strftime('%Y-%m-%d')
        self.conn.execute("""
            INSERT INTO drink_log (date, drink, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT (date,drink) DO UPDATE SET quantity = quantity + 1
        """, (today, drink, 1))
        self.conn.commit()

    def main(self):
        while True:
            choice = input('Type command: ')

            readline.add_history(choice)
            readline.write_history_file(self.histfile)

            if " " in choice:
                command, label = choice.split(" ", 1)
            else:
                command = choice
                label = None
            base_datetime = datetime.now()
            match command:
                case "log":
                    if not label:
                        label = input("Insert label: ")
                    self.insert_log(base_datetime, label)
                case "retro":
                    if not label:
                        label = input("Insert \"[minutes ago] [label]\": ")
                    if " " in label:
                        minutes, label = label.split(" ", 1)
                        if minutes.isdigit():
                            retro_datetime = base_datetime - timedelta(minutes=int(minutes))
                            self.insert_log(retro_datetime, label)
                        else:
                            print("Invalid minutes value.")
                    else:
                        print("Invalid value: \"[minutes ago] [label]\"")
                case "today":
                    self.show_today_summary()
                case "end_day":
                    self.end_day()
                case "pause":
                    self.close_current_log()
                    print('You are currently\033[91m paused\033[0m. No task is logged.')
                case "clear":
                    self.refresh_duckdb()
                case "drink":
                    if not label:
                        label = input("Which drink?: ")
                    self.log_drink(label)
                case "exit":
                    self.close_current_log()
                    self.conn.commit()
                    break

if __name__ == "__main__":
    programme = TimeTracker()