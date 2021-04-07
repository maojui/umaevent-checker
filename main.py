#! /usr/bin/python
import cv2
import time
import numpy as np
from mss import mss
import json
import pytesseract
import tkinter as tk
from PIL import Image, ImageTk, ImageOps
from functools import partial
from win32gui import FindWindow, GetWindowRect
import pywintypes
import difflib 
import multiprocessing

Debug = False

pytesseract.pytesseract.tesseract_cmd = 'Tesseract-OCR\\tesseract.exe'
sct = mss()
screen = umamusume = None
characters = json.load(open('asset/json/character.json','rb'))
event_data = json.load(open('asset/json/events.json','rb'))

# musume selected.
uma_events = None
uma = None
uma_id = None

character_figsize = (70,70)
character_col = 6
character_pad = 5

def lcs(X, Y, m, n):
    if m == 0 or n == 0:
       return 0
    elif X[m-1] == Y[n-1]:
       return 1 + lcs(X, Y, m-1, n-1)
    else:
       return max(lcs(X, Y, m, n-1), lcs(X, Y, m-1, n))


def updateUma(id):
    global uma_id, uma, uma_events
    uma_id = id+1
    uma = characters[str(uma_id)]
    uma_events = event_data[uma]

class Page(tk.Frame):
    
    def __init__(self, *args, **kwargs):
        tk.Frame.__init__(self, *args, **kwargs)
    
    def show(self):
        self.lift()
        
# Select the uma musume which user choose to raise up.
class UmaPicker(Page):

    def __init__(self, *args, **kwargs):
        Page.__init__(self, *args, **kwargs)
        self.images = [None] * len(characters.keys())
        self.buttons = [None] * len(characters.keys())
        self.load_character()
        
    def load_character(self):
        for idx, key in enumerate(characters.keys()):
            try :
                image = Image.open(f"asset/images/character/i_{key}.png")
                image = image.resize(character_figsize, Image.ANTIALIAS)
                self.images[idx] = ImageTk.PhotoImage(image)
            except Exception as ex:
                print("Character image loading error.")
                print(str(ex))
            finally:
                self.buttons[idx] = tk.Button(self, text=idx, image=self.images[idx], command=lambda c=idx: self.click(self.buttons[c].cget("text")))
        self.select_character(-1)


    def select_character(self, index):
        for idx, key in enumerate(characters.keys()):
            if idx == index :
                self.buttons[idx].config(borderwidth=4, relief=tk.SOLID)
                self.buttons[idx].grid(column=idx%character_col,row=idx//character_col, padx=character_pad-2, pady=character_pad-2)
            else :
                self.buttons[idx].config(borderwidth=2, relief=tk.RAISED)
                self.buttons[idx].grid(column=idx%character_col,row=idx//character_col, padx=character_pad, pady=character_pad)

    def click(self, idx):
        global uma
        self.select_character(idx)
        updateUma(idx)
        p2.show()
        p2.run()

class EventReader(Page):

    def __init__(self, *args, **kwargs):
        Page.__init__(self, *args, **kwargs)
        self.font_size = tk.Scale(self, from_=10, to=200, orient=tk.HORIZONTAL)#, command=self.update)
        self.font_size.set(32)
        self.image = None
        self.musume_button = tk.Button(self, image=None, command=self.stop)
        self.event_label = None
        self.option_labels = []
        self.option_results = []
        for i in range(5):
            self.option_labels.append(tk.Label(self, height=1))
            self.option_results.append(tk.Label(self, height=1))
        self.is_active = False
        self.fps = 1
        
    def get_screen_position(self):
        try :
            window_handle = FindWindow(None, "umamusume")
            window_rect   = GetWindowRect(window_handle)
            left, top, right, bottom = window_rect
            mon = {'left': left+8, 'top': top+2, 'width': right-left-16, 'height': bottom-top-16}
            return mon
        except pywintypes.error:
            return None

    def get_OCR(self, img):
        content = pytesseract.image_to_string(img, lang='jpn')
        return content.strip()

    def choices_detector(self, screenshot, size):
        width, height = size 
        left = int(width * 10/1000)
        top = 30+int(height * 230/1000)
        width = int(width * 990/1000)
        height = int(height * 460/1000)
        choice_block = screenshot.crop((left, top, left+width, top+height))
        
        # Change to opencv and detect rectangle block
        img = cv2.cvtColor(np.array(choice_block), cv2.COLOR_RGB2BGR)
        imgGry = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret , thrash = cv2.threshold(imgGry, 240 , 255, cv2.CHAIN_APPROX_TC89_L1)
        contours , hierarchy = cv2.findContours(thrash, cv2.RETR_EXTERNAL , cv2.CHAIN_APPROX_SIMPLE)

        # Collect the options
        try :
            choices = []
            for contour in contours:
                approx = cv2.approxPolyDP(contour, 0.01* cv2.arcLength(contour, True), True)
                cv2.drawContours(img, [approx], 0, (0, 0, 0), 5)
                x = approx.ravel()[0]
                y = approx.ravel()[1] - 5
                if len(approx) == 4 :
                    x, y , w, h = cv2.boundingRect(approx)
                    aspectRatio = float(w)/h
                    block = choice_block.crop((40+x, y, x+w-55, y+h))
                    w,h = block.size
                    if w==0 or h==0 :
                        continue
                    choices.append(block)
            return choices[::-1]
        except :
            return []

    def get_event(self, screenshot, size) :
        if self.font_size == None :
            return None
        width, height = size 
        
        left = 3+int(width * 150/1000)
        top = 30+int(height * 180/1000)
        width = int(width * 550/1000)
        height = int(height * 35/1000)

        raw_event = screenshot.crop((left, top, left+width, top+height))
        self.raw_event = ImageTk.PhotoImage(raw_event)
        event = raw_event.convert('L')
        event = ImageOps.invert(event)
        # # To Bitmap
        # event = np.array(event)
        # event = np.array((event>30)*255, dtype=np.uint8)
        # event = Image.fromarray(event)
        if Debug :
            cv2.imshow('event captured.', np.array(event) )
        return raw_event, event
        
    def get_info(self, skip=False, *args):
        umamusume = self.get_screen_position()
        if umamusume == None : 
            self.screenshot = None
            return None
        else :
            screen = sct.grab(monitor=umamusume)
            screenshot = Image.frombytes('RGB', (screen.width, screen.height), screen.rgb)
            self.screenshot = screenshot
            # Get game states
            self.raw_event, self.event = self.get_event(screenshot, (screen.width, screen.height))
            if skip :
                w,h = self.event.size
                self.event = self.event.crop((40, 0, w, h))
            event_string = self.get_OCR(self.event)
            event_string = event_string.replace('/', '!')
            if event_string :
                # TODO : More check for options
                self.options = self.choices_detector(screenshot, (screen.width, screen.height))
                option_strings = []
                for option in self.options :
                    option_strings.append(self.get_OCR(option))
                return (event_string, option_strings)
            return None

        
    def update(self, *args):
        global uma_events
        if self.is_active == False :
            self.closed = True
            return
        event = self.get_info()
        if self.event_label != None :
            self.event_label.destroy()
        self.raw_event = ImageTk.PhotoImage(self.raw_event)
        self.event_label = tk.Label(self, image=self.raw_event)
        self.event_label.grid(row=0, column=1, pady=10)
        if event == None :
            event = self.get_info(skip=True)
        if self.screenshot == None or event == None:
            pass
        else :
            name, options = event
            
            # self.event_label.config(text=name, image = ImageTk.PhotoImage(self.raw_event))
            # self.event_label.grid(row=0, column=1)
            # for key in self.data[self.uma].keys() :
            # name = name.split(' ')[0]
            keys = difflib.get_close_matches(name, uma_events.keys())
            print("Capture event name :", name)
            print("Closest event :", keys)
            counter = 0
            if len(keys) > 0 :
                event_name = keys[0]
                results = uma_events[event_name]
                # Character
                if type(results) == list :
                    for idx, result in enumerate(results) :
                        self.option_labels[idx].config(text=result['n'], borderwidth=4, relief=tk.SOLID)
                        height = result['t'].count('\n') + 1
                        self.option_results[idx].config(text=result['t'], height=height, borderwidth=4, relief=tk.SOLID)
                        counter += 1
                # Support Card
                elif type(results) == dict : 
                        for level in ['SSR', 'SR', 'R', ''] :
                            if level in results :
                                for idx, result in enumerate(results[level]) :
                                    self.option_labels[idx].config(text=result['n'], borderwidth=4, relief=tk.SOLID)
                                    height = result['t'].count('\n') + 1
                                    self.option_results[idx].config(text=result['t'], height=height, borderwidth=4, relief=tk.SOLID)
                                    counter += 1
                                break
                        else :
                            raise ValueError("Something go wrong ... Support card's level is not in 'SRR', 'SR', 'R', ''")
            for i in range(counter) :
                self.option_labels[i].grid(row=i+1, column=0, padx=1, pady=1, sticky='w')
                self.option_results[i].grid(row=i+1, column=1, padx=1, pady=1, sticky='w')
            for i in range(counter, 5) :
                self.option_labels[i].grid_forget()
                self.option_results[i].grid_forget()
            # print("CLEAN")

        self.after( int(1000/self.fps), self.update)

    def run(self):
        print("Start capture")
        self.closed = False
        global uma_id
        self.is_active = True
        self.image = Image.open(f"asset/images/character/i_{uma_id}.png")
        self.image = self.image.resize((70, 70), Image.ANTIALIAS)
        self.image = ImageTk.PhotoImage(self.image)
        self.musume_button.config(image=self.image)
        self.musume_button.grid(row=0, column=0, pady=10)
        self.update()
    
    def stop(self):
        print("Stop capture")
        self.is_active = False
        p1.show()

class MainApp(tk.Frame) :

    def __init__(self, *args, **kwargs):
        
        tk.Frame.__init__(self, *args, **kwargs)
        
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        p1.place(in_=container, x=0, y=0, relwidth=1, relheight=1)
        p2.place(in_=container, x=0, y=0, relwidth=1, relheight=1)

        p1.show()

        self.bind("q", self.close)
        self.bind("<Escape>", self.close)
        self.focus_set()
    
    def close(self, *args):
        self.quit()
        print("mainloop quit")

# if __name__ == '__main__':
root = tk.Tk(className='Umamusume - Event capture')
p1 = UmaPicker(root)
p2 = EventReader(root)
main = MainApp(root)
main.pack(side="top", fill="both", expand=True)
root.wm_attributes("-transparentcolor", 'grey')
root.geometry("520x440")
root.mainloop()