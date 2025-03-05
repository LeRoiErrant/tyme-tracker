import duckdb
import pandas as pd
from datetime import datetime
from pynput import keyboard
from threading import Thread
import os

class TimeTracker:
    def __init__(self, db_file='time_tracker.db'):
        os.system('cls' if os.name == 'nt' else 'clear')

        print(" ▗▄▄▖▗▖ ▗▖▗▄▄▖  ▗▄▖ ▗▖  ▗▖ ▗▄▖  ▗▄▄▖")
        print("▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▛▚▖▐▌▐▌ ▐▌▐▌   ")
        print("▐▌   ▐▛▀▜▌▐▛▀▚▖▐▌ ▐▌▐▌ ▝▜▌▐▌ ▐▌ ▝▀▚▖")
        print("▝▚▄▄▖▐▌ ▐▌▐▌ ▐▌▝▚▄▞▘▐▌  ▐▌▝▚▄▞▘▗▄▄▞▘\n")


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
                task_id TEXT
            )
        ''')

    def close_current_log(self):
        if self.last_insert_id:
            time = datetime.now().strftime('%H:%M')
            update_query = """
                        UPDATE time_log
                        SET time_end = ?
                        WHERE id = ?
                    """
            self.conn.execute(update_query, (time, self.last_insert_id))

    def insert_log(self, label):
        self.close_current_log()
        base_datetime = datetime.now()
        date = base_datetime.strftime('%Y-%m-%d')
        time = base_datetime.strftime('%H:%M')

        result = self.conn.execute("INSERT INTO time_log (date,time_start, label) VALUES (?, ?, ?)  RETURNING (id)",
                          (date, time, label)).fetchone()
        if result:
            self.last_insert_id = result[0]

    def listen_shortcut(self):
        with keyboard.GlobalHotKeys({'<ctrl>+<alt>+t': self.focus_terminal}) as listener:
            listener.join()

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
            while not task_id:
                task_id = input(f"Enter task id for \"{log[0]} [{log[1]} - {log[2]}] {log[3]}\": ")
            self.conn.execute("""
                        UPDATE time_log
                        SET task_id = ?
                        WHERE id = ?
                    """, (task_id, log[4]))

    def main(self):
        while True:
            choice = input('Type command: ')

            if " " in choice:
                command, label = choice.split(" ", 1)
            else:
                command = choice
                label = None

            match command:
                case "log":
                    if not label:
                        label = input("Insert label: ")
                    self.insert_log(label)
                case "today":
                    self.show_today_summary()
                case "end_day":
                    self.end_day()
                case "clear":
                    self.refresh_duckdb()
                case "exit":
                    self.close_current_log()
                    break

if __name__ == "__main__":
    programme = TimeTracker()