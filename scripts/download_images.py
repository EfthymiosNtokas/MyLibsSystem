import requests
import os

# Using readlines()
urls_raw = open('images.txt', 'r')
urls = urls_raw.readlines()
 
isExist = os.path.exists('../images')
if not isExist:
   # Create a new directory because it does not exist
   os.makedirs('../images')

count = 0
# Strips the newline character
for url in urls:
    count += 1
    img_data = requests.get(url.strip()).content
    with open('../images/img_'+str(count)+'.jpg', 'wb') as handler:
        handler.write(img_data)
handler.close()
urls_raw.close()