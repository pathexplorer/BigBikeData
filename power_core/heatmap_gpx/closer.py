"""
Adding closer tag to heatmap file before direct using in OSM or JOSM
Work locally
"""
import sys
import re
closer_tag="</gpx>"
def check_if_exist(filename: str) -> str | None:
    with open(filename, "r", encoding="utf-8") as file:
        lines=file.readlines()[-2:]
        combined = "".join(lines)
        find = re.search(closer_tag,combined)
        if find:
            print("Error! Closer tag already present"+"\n"+f"{combined}")
            return None
        else:
            add_closer(filename)
            print("Two last line"+"\n"+f"{combined}")
            print("Tag doesnt exist, adding...")
            return None
def add_closer(filename: str) -> str | None:
    with open(filename, "a", encoding="utf-8") as f:
        f.write(closer_tag)
    print("Adding successfully")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]
    check_if_exist(filename)





