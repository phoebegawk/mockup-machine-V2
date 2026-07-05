
import cv2
import tkinter as tk
from tkinter import filedialog

# Ask the user to pick an image file
root = tk.Tk()
root.withdraw()
file_path = filedialog.askopenfilename(title="Choose a billboard mockup image")

if not file_path:
    print("❌ No file selected.")
    exit()

img = cv2.imread(file_path)
clicked_points = []

def click_event(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        clicked_points.append((x, y))
        print(f"Point {len(clicked_points)}: ({x}, {y})")
        cv2.circle(img, (x, y), 5, (0, 255, 0), -1)
        cv2.imshow("Click the 4 corners of the billboard (TL, TR, BR, BL)", img)
        if len(clicked_points) == 4:
            print("\n✅ Final coordinates (copy into script):")
            print('    "[INSERT NAME HERE]": [')
            for pt in clicked_points:
                print(f"        {pt},")
            print('    ],')
            cv2.waitKey(0)
            cv2.destroyAllWindows()

cv2.imshow("Click the 4 corners of the billboard (TL, TR, BR, BL)", img)
cv2.setMouseCallback("Click the 4 corners of the billboard (TL, TR, BR, BL)", click_event)
cv2.waitKey(0)
cv2.destroyAllWindows()
