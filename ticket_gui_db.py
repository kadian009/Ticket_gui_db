import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import sqlite3, os, pandas as pd, qrcode
from PIL import Image, ImageTk
import cv2
from pyzbar.pyzbar import decode
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "tickets.db")
CSV_FILE = os.path.join(BASE_DIR, "raw_bus_data.csv")

# ---------- Database Setup ----------
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS bookings")
cur.execute("DROP TABLE IF EXISTS validation_logs")

cur.execute("""
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger TEXT,
    route TEXT,
    time TEXT,
    fare REAL,
    status TEXT DEFAULT 'Booked'
)
""")

cur.execute("""
CREATE TABLE validation_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER,
    method TEXT,
    timestamp TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
)
""")
conn.commit()

# ---------- GUI ----------
root = tk.Tk()
root.title("Bus Ticket Booking System")
root.geometry("900x700")

# ---------- Load Routes ----------
def load_routes():
    if not os.path.exists(CSV_FILE):
        messagebox.showerror("Error", f"CSV file not found!\nPlace {CSV_FILE} next to script.")
        return []
    try:
        df = pd.read_csv(CSV_FILE)
        return df
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load routes: {e}")
        return []

routes_df = load_routes()

# ---------- Book Ticket ----------
def book_ticket():
    passenger = entry_name.get().strip()
    selected = route_box.curselection()
    if not passenger or not selected:
        messagebox.showwarning("Warning", "Enter passenger name and select a route")
        return
    route = routes_df.iloc[selected[0]]
    bus_no, src, dest, time, fare = route["BusNo"], route["Source"], route["Destination"], route["Time"], route["Fare"]
    route_str = f"{bus_no}: {src}-{dest}"

    cur.execute("INSERT INTO bookings (passenger, route, time, fare) VALUES (?,?,?,?)",
                (passenger, route_str, time, fare))
    conn.commit()
    booking_id = cur.lastrowid

    # QR content
    qr_data = f"BookingID:{booking_id}|Passenger:{passenger}|Route:{route_str}|Time:{time}|Fare:{fare}"
    qr_img = qrcode.make(qr_data)
    qr_path = os.path.join(BASE_DIR, f"ticket_{booking_id}.png")
    qr_img.save(qr_path)

    # Show QR
    qr_win = tk.Toplevel(root)
    qr_win.title(f"QR Code - Booking {booking_id}")
    qr_win.geometry("300x300")
    qr_photo = ImageTk.PhotoImage(Image.open(qr_path))
    qr_label = tk.Label(qr_win, image=qr_photo)
    qr_label.image = qr_photo
    qr_label.pack(expand=True)

    messagebox.showinfo("Success", f"Booking successful!\nBooking ID: {booking_id}")
    load_bookings()

# ---------- Add Validation Log ----------
def add_log(booking_id, method):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO validation_logs (booking_id, method, timestamp) VALUES (?,?,?)",
                (booking_id, method, timestamp))
    conn.commit()
    load_logs()

# ---------- Validate from Image ----------
def validate_from_image():
    file_path = filedialog.askopenfilename(filetypes=[("PNG Images","*.png")])
    if not file_path: return
    img = Image.open(file_path)
    decoded = decode(img)
    if not decoded:
        messagebox.showerror("Error", "No QR code found in image")
        return
    qr_text = decoded[0].data.decode()
    if "BookingID:" not in qr_text:
        messagebox.showerror("Error", "Invalid QR code")
        return
    booking_id = qr_text.split("|")[0].replace("BookingID:","")
    cur.execute("UPDATE bookings SET status=? WHERE id=?",
                ("Validated", booking_id))
    conn.commit()
    add_log(booking_id, "Image")
    messagebox.showinfo("Success", f"Booking {booking_id} validated from image")
    load_bookings()

# ---------- Validate via Webcam ----------
def validate_via_webcam():
    cap = cv2.VideoCapture(0)
    found = False
    booking_id = None
    while True:
        ret, frame = cap.read()
        if not ret: break
        for qr in decode(frame):
            qr_text = qr.data.decode()
            if "BookingID:" in qr_text:
                booking_id = qr_text.split("|")[0].replace("BookingID:","")
                cur.execute("UPDATE bookings SET status=? WHERE id=?",
                            ("Validated", booking_id))
                conn.commit()
                add_log(booking_id, "Webcam")
                found = True
                cv2.putText(frame, f"Validated {booking_id}", (50,50), cv2.FONT_HERSHEY_SIMPLEX, 
                            1, (0,255,0), 2)
                break
        cv2.imshow("Scan QR - Press Q to exit", frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or found: break
    cap.release()
    cv2.destroyAllWindows()
    if found:
        messagebox.showinfo("Success", f"Booking {booking_id} validated via webcam")
        load_bookings()
    else:
        messagebox.showwarning("Info", "No valid QR scanned")

# ---------- Load Bookings ----------
def load_bookings():
    for row in bookings_table.get_children():
        bookings_table.delete(row)
    for row in cur.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT 20"):
        bookings_table.insert("", "end", values=row)

# ---------- Load Validation Logs ----------
def load_logs():
    for row in logs_table.get_children():
        logs_table.delete(row)
    for row in cur.execute("SELECT * FROM validation_logs ORDER BY log_id DESC LIMIT 20"):
        logs_table.insert("", "end", values=row)

# ---------- Export ----------
def export_bookings():
    export_file = os.path.join(BASE_DIR, "bookings_export.csv")
    df = pd.read_sql_query("SELECT * FROM bookings", conn)
    df.to_csv(export_file, index=False)
    messagebox.showinfo("Exported", f"Bookings exported to {export_file}")

# ---------- UI ----------
tk.Label(root, text="Passenger Name:").pack(pady=5)
entry_name = tk.Entry(root)
entry_name.pack(pady=5)

tk.Label(root, text="Available Routes:").pack(pady=5)
route_box = tk.Listbox(root, width=70, height=6)
route_box.pack()
for idx, row in routes_df.iterrows():
    route_box.insert(tk.END, f"{row['BusNo']}: {row['Source']} -> {row['Destination']} @ {row['Time']} ₹{row['Fare']}")

tk.Button(root, text="🎟️ Book Ticket & Generate QR", command=book_ticket, bg="lightgreen").pack(pady=5)
tk.Button(root, text="🖼️ Validate from Image", command=validate_from_image, bg="lightblue").pack(pady=5)
tk.Button(root, text="📷 Validate via Webcam", command=validate_via_webcam, bg="orange").pack(pady=5)

# Bookings Table
tk.Label(root, text="📚 Recent Bookings:").pack(pady=10)
columns = ("ID","Passenger","Route","Time","Fare","Status")
bookings_table = ttk.Treeview(root, columns=columns, show="headings", height=8)
for col in columns:
    bookings_table.heading(col, text=col)
    bookings_table.column(col, width=120)
bookings_table.pack(pady=5)

# Validation Logs Table
tk.Label(root, text="📝 Validation Logs:").pack(pady=10)
log_columns = ("LogID","BookingID","Method","Timestamp")
logs_table = ttk.Treeview(root, columns=log_columns, show="headings", height=6)
for col in log_columns:
    logs_table.heading(col, text=col)
    logs_table.column(col, width=150)
logs_table.pack(pady=5)

tk.Button(root, text="Export Bookings", command=export_bookings, bg="lightgrey").pack(pady=10)

# Initial Load
load_bookings()
load_logs()

root.mainloop()
