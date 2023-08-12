from datetime import datetime, timedelta

data = [
(20, 3, 1296, '2022-01-01', '2022-01-08', '2022-01-04'),
(21, 3, 1297, '2022-01-01', '2022-01-08', '2022-01-04'),
(22, 3, 1298, '2022-01-01', '2022-01-08', '2022-01-04'),
(23, 3, 1299, '2022-01-01', '2022-01-08', '2022-01-04'),
(24, 3, 1300, '2022-01-01', '2022-01-08', '2022-01-04'),
(25, 3, 1301, '2022-01-01', '2022-01-08', '2022-01-04'),
(26, 3, 1302, '2022-01-01', '2022-01-08', '2022-01-04'),
(27, 3, 1232, '2022-01-01', '2022-01-08', '2022-01-04'),
(28, 3, 1233, '2022-01-01', '2022-01-08', '2022-01-04'),
]

new_data = []

for entry in data:
    new_entry = list(entry)
    for i in range(3, 6):
        date = datetime.strptime(entry[i], '%Y-%m-%d')
        new_date = date + timedelta(days=15)
        new_date = new_date.replace(month=new_date.month + 6)
        new_entry[i] = new_date.strftime('%Y-%m-%d')
    new_data.append(tuple(new_entry))

# Print the updated data
for entry in new_data:
    s = str(entry) + ','
    print(s)