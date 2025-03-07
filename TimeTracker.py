import duckdb
import pandas as pd
from datetime import datetime, timedelta
from pynput import keyboard
from threading import Thread
import os
import readline
import argparse
import shlex
from icecream import ic

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        if message.startswith('argument command: invalid choice:'):
            return
        else:
            print(message)

class TimeTracker:
    def __init__(self, db_file='time_tracker.db'):
        os.system('cls' if os.name == 'nt' else 'clear')

        print(" ▗▄▄▖▗▖ ▗▖▗▄▄▖  ▗▄▖ ▗▖  ▗▖ ▗▄▖  ▗▄▄▖")
        print("▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▛▚▖▐▌▐▌ ▐▌▐▌   ")
        print("▐▌   ▐▛▀▜▌▐▛▀▚▖▐▌ ▐▌▐▌ ▝▜▌▐▌ ▐▌ ▝▀▚▖")
        print("▝▚▄▄▖▐▌ ▐▌▐▌ ▐▌▝▚▄▞▘▐▌  ▐▌▝▚▄▞▘▗▄▄▞▘\n")

        self.histfile = os.path.expanduser(os.path.dirname(os.path.abspath(__file__))) + "/.input_history"

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

    def create_parser(self):
        parser = ArgumentParser(description="Time Tracker CLI", add_help=True)

        subparsers = parser.add_subparsers(dest="command")

        abstract_log_parser = ArgumentParser()
        abstract_log_parser.add_argument("label", help="Task short description")

        subparsers.add_parser("log", help="Log a new task")

        retro_parser = subparsers.add_parser("retro", help="Log a task retroactively")
        retro_parser.add_argument('minutes', help="Number of minute in the past")

        drink_parser = subparsers.add_parser("drink", help="Log a drink")
        drink_parser.add_argument("drink", help="What type of drink", choices=['water', 'coffee', 'soda', 'alcohol'])

        subparsers.add_parser("today", help="Display today's logged tasks")
        subparsers.add_parser("end_day", help="Close tasks and enter task's ID")
        subparsers.add_parser("pause", help="Close current task while keeping the program alive")
        subparsers.add_parser("exit", help="Exit Time Tracker")
        subparsers.add_parser("help", help="Show available commands")

        return parser

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
        parser = self.create_parser()

        while True:
            try:
                command_input = input("\n> ")

                #readline.add_history(command_input)
                #readline.write_history_file(self.histfile)

                args, unknown_args = parser.parse_known_args(shlex.split(command_input))

                ic(unknown_args)
                if unknown_args:
                    print("Unknown command. Type 'help' to see the available commands.")
                    continue

                base_datetime = datetime.now()

                match args.command:
                    case "log":
                        self.insert_log(base_datetime, args.label)
                    case "retro":
                        retro_datetime = base_datetime - timedelta(minutes=int(args.minutes))
                        self.insert_log(retro_datetime, args.label)
                    case "today":
                        self.show_today_summary()
                    case "end_day":
                        self.end_day()
                    case "pause":
                        self.close_current_log()
                        print('You are currently\033[91m paused\033[0m. No task is logged.')
                    case "drink":
                        self.log_drink(args.drink)
                    case "exit":
                        self.close_current_log()
                        self.conn.commit()
                        break
                    #case "clear":
                    #    self.refresh_duckdb()
            except SystemExit:
                pass
            except Exception as e:
                print(f"Error : {e}")

if __name__ == "__main__":
    programme = TimeTracker()