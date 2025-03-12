import duckdb
import pandas as pd
from datetime import datetime, timedelta

from customtkinter import CTkEntry
from pynput import keyboard, mouse
from threading import Thread
import os
import readline
import argparse
import shlex
from icecream import ic
import tkinter as tk
from tkinter import Toplevel, Label, ttk
import customtkinter as ctk

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        if message.startswith('argument command: invalid choice:'):
            return
        else:
            print(message)

class TimeTracker:
    def __init__(self, db_file='time_tracker.db'):
        self.chrono_label = None
        self.window_area = None
        self.table = None
        os.system('cls' if os.name == 'nt' else 'clear')

        print(" ▗▄▄▖▗▖ ▗▖▗▄▄▖  ▗▄▖ ▗▖  ▗▖ ▗▄▖  ▗▄▄▖")
        print("▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▛▚▖▐▌▐▌ ▐▌▐▌   ")
        print("▐▌   ▐▛▀▜▌▐▛▀▚▖▐▌ ▐▌▐▌ ▝▜▌▐▌ ▐▌ ▝▀▚▖")
        print("▝▚▄▄▖▐▌ ▐▌▐▌ ▐▌▝▚▄▞▘▐▌  ▐▌▝▚▄▞▘▗▄▄▞▘\n")

        self.histfile = os.path.expanduser(os.path.dirname(os.path.abspath(__file__))) + "/.input_history"

        self.buttons_pad_y = 10
        self.buttons_pad_x = 10
        self.buttons_frame_height = 5 * ((2 * self.buttons_pad_y) + 30)
        self.buttons_frame_width = 150
        self.table_frame_width = 600
        self.base_geometry = str(self.buttons_frame_width) + "x" + str(self.buttons_frame_height)
        self.enlarged_geometry = str(self.buttons_frame_width + self.table_frame_width) + "x400"
        self.enlarged = False
        self.win = self.config_window()

        if not os.path.exists(self.histfile):
            open(self.histfile, 'w').close()
        try:
            readline.read_history_file(self.histfile)
        except FileNotFoundError:
            ic("File not found")

        listener_thread = Thread(target=self.listen_shortcut, daemon=True)
        listener_thread.start()
        self.last_insert_id = None
        self.conn = duckdb.connect(db_file)
        self.init_db()

        self.button_frame = self.config_buttons_frame()
        self.table = self.config_table_frame()
        self.win.update_idletasks()
        self.get_window_position()

        self.listener = mouse.Listener(on_move=self.on_mouse_move)
        self.listener.start()

        self.fill_table()
        self.win.mainloop()

    def config_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        win = ctk.CTk()

        win.geometry(self.base_geometry)
        win.attributes('-topmost', 1)
        win.attributes("-alpha", 0.7)
        return win

    def config_buttons_frame(self, ):
        btn_frame = ctk.CTkFrame(self.win, width=self.buttons_frame_width)
        btn_frame.pack(side=ctk.LEFT, fill="both", expand=True)
        self.chrono_label = tk.Label(btn_frame, text="00:00:00", font=("Arial", 14))
        self.chrono_label.pack(padx=self.buttons_pad_x, pady=self.buttons_pad_y)
        self.update_time()

        self.add_button(btn_frame, "Log task", self.open_log_popup)
        self.add_button(btn_frame, "Stop", self.close_current_log, fg_color="#57A0D2", hover_color="#4682B4")
        self.add_button(btn_frame, "Show current log", self.enlarge_window)
        self.add_button(btn_frame, "Exit", self.exit_gui, fg_color="#b20000", hover_color="#e50000")
        return btn_frame

    def add_button(self, parent, label, command, fg_color = None, hover_color = None):
        button_width = self.buttons_frame_width - (2 * self.buttons_pad_x)
        button = ctk.CTkButton(parent, width=button_width, text=label, command=command, fg_color=fg_color, hover_color=hover_color)
        button.pack(pady=self.buttons_pad_y, padx=self.buttons_pad_x)
        return button

    def config_table_frame(self):
        table_frame = ctk.CTkFrame(self.win, width=self.table_frame_width)
        table_frame.pack(side=ctk.LEFT, fill="both", expand=True)
        table_config = {
            'id': {
                'header': 'ID',
                'width': 100
            },
            'date': {
                'header': 'Date',
                'width': 100
            },
            'hour_start': {
                'header': 'Start',
                'width': 100
            },
            'hour_end': {
                'header': 'End',
                'width': 100
            },
            'label': {
                'header': 'Label',
                'width': 100
            },
            'task_id': {
                'header': 'Task',
                'width': 100
            }
        }
        table_columns = tuple(table_config.keys())
        table = ttk.Treeview(table_frame, columns=table_columns, show='headings')

        for column in table_columns:
            table.heading(column, text=table_config[column]['header'])
            table.column(column, width=table_config[column]['width'])

        table.bind('<<TreeviewSelect>>', self.update_row)
        table.pack(expand=True, fill="both")
        return table

    def calculate_work_time(self):
        today_str = datetime.today().strftime('%Y-%m-%d')
        query = "SELECT time_start, time_end FROM time_log WHERE time_start IS NOT NULL AND date = ?;"
        rows = self.conn.execute(query, (today_str,)).fetchall()

        total_seconds = 0
        now = datetime.now()
        today = now.date()
        for hour_start, hour_end in rows:
            start_time = datetime.strptime(hour_start, "%H:%M").replace(year=today.year, month=today.month, day=today.day)
            if hour_end:
                end_time = datetime.strptime(hour_end, "%H:%M").replace(year=today.year, month=today.month, day=today.day)
            else:
                end_time = now
            total_seconds += (end_time - start_time).total_seconds()

        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"{hours:02}:{minutes:02}"

    def update_time(self):
        work_time = self.calculate_work_time()
        self.chrono_label.config(text=f"{work_time}")
        self.win.after(int(60000), self.update_time)

    def update_row(self, _):
        for item in self.table.selection():
            values = self.table.item(item)['values']
            edit = ctk.CTkToplevel(self.win)
            edit.geometry("300x300")
            edit.attributes('-topmost', 1)
            edit.title("Log task")
            column_names = ["Date", "Time Start", "Time End", "Label", "Task ID"]

            entries = []
            for i in range(1, len(values)):
                frame = ctk.CTkFrame(edit)
                frame.pack(pady=10)
                ctk.CTkLabel(frame, text=column_names[i - 1]).pack(side=tk.LEFT, padx=5)
                entry = ctk.CTkEntry(frame)
                entry.insert(0, str(values[i]))
                entry.pack(side=tk.LEFT)
                entries.append(entry)

            def save_changes():
                new_values = [values[0]] + [entry.get() for entry in entries]
                query = """
                        UPDATE time_log
                        SET date = ?, time_start = ?, time_end = ?, label = ?, task_id = ?
                        WHERE id = ?
                    """
                self.conn.execute(query, tuple(new_values[1:] + [new_values[0]]))
                self.conn.commit()
                self.table.item(item, values=new_values)
                edit.destroy()

            save_button = ctk.CTkButton(edit, text="Save", command=save_changes)
            save_button.pack(pady=10)

    def fill_table(self):
        today = datetime.today().strftime('%Y-%m-%d')
        query = """SELECT id, date,time_start, time_end, label, task_id
                    FROM time_log
                    WHERE date = ?
                """
        data = self.conn.execute(query, (today,)).fetchall()
        self.table.delete(*self.table.get_children())
        for item in data:
            self.table.insert("", "end", values=item)

    def get_window_position(self):
        self.win.update_idletasks()
        x = self.win.winfo_x()
        y = self.win.winfo_y()
        width = self.win.winfo_width()
        height = self.win.winfo_height()
        self.window_area = (x, y, x + width, y + height)

    def on_mouse_move(self, x, y):
        self.get_window_position()
        x1, y1, x2, y2 = self.window_area

        marge = 100
        if (x1 - marge) <= x <= (x2 + marge) and (y1 - marge) <= y <= (y2 + marge):
            self.win.attributes("-alpha", 1.0)
        else:
            self.win.attributes("-alpha", 0.7)
            if self.enlarged:
                self.enlarge_window()

    def create_parser(self):
        parser = ArgumentParser(description="Time Tracker CLI", add_help=True)

        subparsers = parser.add_subparsers(dest="command")

        abstract_log_parser = ArgumentParser()
        abstract_log_parser.add_argument("label", help="Task short description")

        log_parser = subparsers.add_parser("log", help="Log a new task")
        log_parser.add_argument("label", help="Task short description")

        retro_parser = subparsers.add_parser("retro", help="Log a task retroactively")
        retro_parser.add_argument("label", help="Task short description")
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

    def enlarge_window(self):
        if self.enlarged:
            self.win.geometry(self.base_geometry)
        else:
            self.win.geometry(self.enlarged_geometry)

        self.enlarged = not self.enlarged

    def insert_log(self, base_datetime, label):
        self.close_current_log(base_datetime)
        date = base_datetime.strftime('%Y-%m-%d')
        time = base_datetime.strftime('%H:%M')

        result = self.conn.execute("INSERT INTO time_log (date,time_start, label) VALUES (?, ?, ?)  RETURNING (id)",
                          (date, time, label)).fetchone()
        self.fill_table()
        if result:
            self.last_insert_id = result[0]

    def for_canonical(self, f):
        return lambda k: f(k)

    def open_log_popup(self):
        self.win.attributes("-alpha", 1)
        logger = ctk.CTkToplevel(self.win)
        logger.geometry("300x50")
        logger.attributes('-topmost', 1)
        logger.title("Log task")


        frame = ctk.CTkFrame(logger)
        frame.pack(pady=10)

        entry = ctk.CTkEntry(frame, width=200)
        entry.pack(side=tk.LEFT, padx=5)
        entry.focus_set()

        def on_enter(event=None):
            label_text = entry.get()
            if label_text:
                self.insert_log(datetime.now(), label_text)
                logger.destroy()
                self.win.attributes("-alpha", 0.7)

        entry.bind("<Return>", on_enter)

        ctk.CTkButton(frame, text="OK", width=70, command=on_enter).pack(side=tk.LEFT)


    def listen_shortcut(self):
        hotkey = keyboard.HotKey(keyboard.HotKey.parse('<ctrl>+<alt>+t'), self.open_log_popup)

        with keyboard.Listener(
            on_press=self.for_canonical(hotkey.press),
            on_release=self.for_canonical(hotkey.release)
        ) as listener:
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


    def refresh_duckdb(self):
        query = """DROP TABLE IF EXISTS time_log"""
        self.conn.query(query)
        self.conn.execute("""DROP SEQUENCE IF EXISTS seq""")
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

    def exit_gui(self):
        self.close_current_log()
        self.conn.commit()
        self.conn.close()
        self.win.destroy()
        self.win.quit()

    def main(self):
        parser = self.create_parser()

        while True:
            try:
                command_input = input("\n> ")

                readline.add_history(command_input)
                readline.write_history_file(self.histfile)

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