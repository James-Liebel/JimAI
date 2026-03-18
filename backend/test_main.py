import traceback
import sys

try:
    import main
    print("Success")
except Exception as e:
    with open("err.txt", "w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
