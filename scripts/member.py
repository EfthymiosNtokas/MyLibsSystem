with open('output.txt', 'w') as file:
    for i in range(6, 16):
        s = "(" + str(i) + ", 5, 2, 1),\n"
        file.write(s)

    for i in range(16, 46):
        s = "(" + str(i) + ", 5, 1, 1),\n"
        file.write(s)

    for i in range(50, 60):
        s = "(" + str(i) + ", 4, 2, 1),\n"
        file.write(s)

    for i in range(60, 90):
        s = "(" + str(i) + ", 4, 1, 1),\n"
        file.write(s)