import numpy as np
import matplotlib.pyplot as plt
import glob
import os
import random

PROCESSED_DIR = "processed_data"
OUTPUT_DIR = "processed_images"
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "summary_grid.png")

def ensure_output_dir():
    if not os.path.exists(OUTPUT_DIR):
         os.makedirs(OUTPUT_DIR)
         print(f"Created directory: {OUTPUT_DIR}")

def visualize_summary_grid(num_samples=9):
    """
    Randomly selects processed .npy files and visualizes them in a grid.
    """
    files = glob.glob(os.path.join(PROCESSED_DIR, "*.npy"))
    
    if not files:
        print(f"No .npy files found in {PROCESSED_DIR}")
        return

    # Select random samples
    # If fewer files than requested, use all of them
    num_samples = min(num_samples, len(files))
    selected_files = random.sample(files, num_samples)
    
    print(f"Generating summary grid with {num_samples} random samples...")

    # Calculate grid size (approximate square)
    grid_size = int(np.ceil(np.sqrt(num_samples)))
    
    fig, axes = plt.subplots(grid_size, grid_size, figsize=(15, 15))
    
    # Handle single sample case (axes is not an array)
    if num_samples == 1:
        axes = np.array([axes])
        
    axes = axes.flatten()
    
    for i, file_path in enumerate(selected_files):
        ax = axes[i]
        try:
            # Load data
            data = np.load(file_path)
            
            # Simple check for shape
            if len(data.shape) == 3 and data.shape[0] == 1:
                 data = data.squeeze()
            
            # Plot heatmap
            im = ax.imshow(data, cmap='viridis') 
            ax.set_title(os.path.basename(file_path), fontsize=8)
            ax.axis('off')
            
            # Add colorbar for the last plot to show scale
            if i == num_samples - 1:
                 plt.colorbar(im, ax=axes, orientation='horizontal', fraction=0.05, pad=0.05, label="Input Value (Kelvin)")

        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            ax.text(0.5, 0.5, "Error", ha='center', va='center')
            ax.axis('off')

    # Hide unused subplots
    for j in range(i + 1, len(axes)):
        axes[j].axis('off')

    plt.tight_layout()
    plt.savefig(SUMMARY_FILE)
    print(f"Summary grid saved to {SUMMARY_FILE}")
    plt.close()

def save_individual_images():
    """
    Generates an image for EVERY processed .npy file.
    """
    files = glob.glob(os.path.join(PROCESSED_DIR, "*.npy"))
    if not files:
        return

    print(f"Generating individual images for {len(files)} files...")
    
    # Setup plot reuse to improve performance
    fig, ax = plt.subplots(figsize=(4, 4))
    
    for i, file_path in enumerate(files):
        try:
            basename = os.path.basename(file_path)
            png_name = basename.replace(".npy", ".png")
            output_path = os.path.join(OUTPUT_DIR, png_name)
            
            # Skip if already exists? Maybe overwrite is safer.
            
            data = np.load(file_path)
            if len(data.shape) == 3 and data.shape[0] == 1:
                 data = data.squeeze()
            
            ax.clear()
            ax.imshow(data, cmap='viridis')
            ax.axis('off')
            ax.set_title(basename, fontsize=8)
            
            plt.savefig(output_path, bbox_inches='tight', pad_inches=0.1)
            
            if (i+1) % 100 == 0:
                print(f"Processed {i+1}/{len(files)}")
                
        except Exception as e:
            print(f"Failed to process {file_path}: {e}")

    plt.close()
    print("All individual images generated.")

if __name__ == "__main__":
    ensure_output_dir()
    visualize_summary_grid()
    save_individual_images()
