import base64
from io import BytesIO

import requests
from PIL import Image

from config import SETTINGS, Paths, load_settings, logger

# Load API key
access_credentials = load_settings(Paths.AUTH["CREDENTIALS"])


# Transformation mapping for shorthand codes or counterclockwise
TRANSFORM_MAP = {
    "h": "flip_h",
    "v": "flip_v",
    "horizontal": "flip_h",
    "vertical": "flip_v",
    "-90": "270",
    "-180": "180",
    "-270": "90",
}


def rotate_or_flip_image(image_url, transformation):
    """
    Download an image from a URL and apply rotation or flip transformation.

    Parameters:
    - image_url (str): URL of the image to process
    - transformation (str): One of '90', '180', '270', 'flip_h', 'flip_v'

    Returns:
    - PIL.Image: Transformed image object
    """
    # Normalize transformation using the map
    transformation = TRANSFORM_MAP.get(transformation, transformation)
    logger.info(f"Image Handling: Downloading image from {image_url}")

    # Download the image
    response = requests.get(image_url)
    response.raise_for_status()

    # Open the image
    img = Image.open(BytesIO(response.content))
    logger.info(
        f"Image Handling: Image downloaded: {img.size[0]}x{img.size[1]} pixels, mode: {img.mode}"
    )

    # Apply transformation
    if transformation == "90":
        img = img.rotate(-90, expand=True)
    elif transformation == "180":
        img = img.rotate(180, expand=True)
    elif transformation == "270":
        img = img.rotate(90, expand=True)
    elif transformation == "flip_h":
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif transformation == "flip_v":
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    else:
        raise ValueError(
            f"Invalid transformation: {transformation}. Use '90', '180', '270', 'flip_h', or 'flip_v'"
        )

    logger.info(f"Image Handling: Applied transformation: {transformation}")
    return img


def upload_to_imgbb(image, title=None):
    """
    Upload a PIL Image to ImgBB and return the URL.

    Parameters:
    - image (PIL.Image): Image object to upload
    - title (str, optional): The name/title of the file

    Returns:
    - str: URL of the uploaded image
    """
    # Load the expiration time from settings (which is stored in days)
    expiration_seconds = SETTINGS["image_retention_age"] * 86400

    api_key = access_credentials["IMGBB_API_KEY"]

    # Convert PIL Image to base64
    buffered = BytesIO()

    # Save as JPEG with 60% quality to reduce file size
    # Convert RGBA to RGB if necessary (JPEG doesn't support transparency)
    if image.mode in ("RGBA", "LA", "P"):
        logger.info(
            f"Image Handling: Converting image from {image.mode} to RGB for JPEG compression"
        )

        # Create a white background
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        rgb_image.paste(
            image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None
        )
        image = rgb_image
    elif image.mode != "RGB":
        image = image.convert("RGB")

    jpeg_quality = SETTINGS["image_jpeg_quality"]
    image.save(buffered, format="JPEG", quality=jpeg_quality)
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    logger.info(
        f"Image Handling: Image encoded to base64 (JPEG quality: {jpeg_quality}%)"
    )

    # Prepare the API request
    url = "https://api.imgbb.com/1/upload"
    payload = {"key": api_key, "image": img_base64, "expiration": expiration_seconds}

    if title:
        payload["name"] = title

    # Make the POST request
    logger.info(
        f"Image Handling: Uploading to ImgBB (expiration: {expiration_seconds}s)"
    )
    response = requests.post(url, data=payload)
    response.raise_for_status()

    # Parse response and return the URL
    result = response.json()

    if result.get("success"):
        logger.info(f"Image uploaded successfully at {result['data']['display_url']}")
        return result["data"]["url"]
    else:
        logger.error(f"Upload failed: {result}")
        raise Exception(f"Upload failed: {result}")


"""TESTING SECTION"""


def show_menu():
    print("\nSelect an operation:")
    print("1. Rotate/Flip image from URL (without uploading)")
    print("2. Rotate/Flip image and upload to ImgBB")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (1-2 or x): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        image_test_url = input("Enter the image URL: ")

        print("\nTransformation options:")
        print("  90  - Rotate 90 degrees clockwise")
        print("  180 - Rotate 180 degrees clockwise (upside-down)")
        print("  270 - Rotate 270 degrees clockwise")
        print("  flip_h - Flip horizontally")
        print("  flip_v - Flip vertically")
        transformation_type = input("Enter transformation: ")

        try:
            if choice == "1":
                img_test = rotate_or_flip_image(image_test_url, transformation_type)
                logger.info(
                    f"Image transformed successfully: {img_test.size} pixels, format: {img_test.format}"
                )
                # Optionally save locally to verify
                save = input("Save locally? (y/n): ")
                if save.lower() == "y":
                    filename = input("Enter filename (e.g., output.png): ")
                    img_test.save(filename)
                    logger.info(f"Saved to {filename}")

            elif choice == "2":
                img_test = rotate_or_flip_image(image_test_url, transformation_type)
                logger.info("Image transformed, uploading to ImgBB...")

                uploaded_url = upload_to_imgbb(img_test)
                print("\nUploaded successfully!")
                logger.info(f"Image URL: {uploaded_url}")

        except Exception as e:
            logger.info(f"Error: {e}")
