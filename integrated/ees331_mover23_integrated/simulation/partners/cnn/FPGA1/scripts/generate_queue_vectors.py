"""Generate the current array-only queue (nine Conv/DW tasks)."""
from pathlib import Path
from array_vectors import generate_queue

def main():
    folder,layers,_=generate_queue(Path(__file__).resolve().parents[1]/'build'/'queue_vectors')
    print(f'Generated {len(layers)} array-only tasks: {folder}')

if __name__=='__main__':main()
