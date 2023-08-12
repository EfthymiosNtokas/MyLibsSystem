import random
#spyrus did this
ISBNS1 = ['9780131988422', '9780138147570', '9780131873742', '9780132618120', '9780134896010', '9780262033848']
ISBNS2 = ['9780961408804', '9780961408811', '9780961408828', '9780521865716', '9780471081100', '9780961408842', '9780199268016', '9780387982588']
ISBNS3 = ['9780138053260', '9781107179868', '9783527406012']
ISBNS4 = ['9782081401224', '9782070443089', '9782080700146', '9782080710817']
ISBNS5 = ['9782253121566', '9782253131501', '9782253140633', '9782253131488', '9782253131532', '9782253130344', '9782253130351', '9782253131495', '9782253131471', '9782253141104']
ISBNS6 = ['9782253098567', '9782253098574', '9782253098581', '9782253098604', '9782253098598', '9782253098611', '9782253098628', '9782253098635', '9782253098642', '9782253098659']
ISBNS7 = ['9780140448078', '9780679734505', '9780679600115', '9780374528379', '9781400079988', '9780307596669', '9780061120064', '9780812970067', '9780375702242']
#edone by efth
ISBN8=['9780747574484', '9780747581086', '9780747581109', '9780747581079', '9780747591054',             '9780545010221', '9781338099133', '9780545582889', '9781408882227']
ISBN9=['9780743477123', '9780143130464', '9780140714548', '9780141396271', '9780743482776',             '9780743482769', '9780143128560', '9780143128614', '9780743482844', '9780141396424']
ISBN10=['9780141439662', '9780141199672', '9780141439518', '9780140434261', '9781234567890',             '9780141389426', '9781503261969', '9780393970775', '9780140431024', '9780486295557']
ISBN11=['9780140439441', '9780486415864', '9780141439563', '9780199536257', '9781853260087',             '9780199219768', '9780199536264', '9780140435122', '9780141439747']

ISBN12=['9780156907392', '9780141183411', '9780701206710', '9780156030156', '9781844087292',             '9780156508497', '9780141183527', '9780156949606', '9781853260285', '9780156947695']
ISBNS= ISBN8+ISBN9+ISBN10+ISBN11+ISBN12

indices = [str(k) for k in range(1, 32)] # 31 categories at the moment

with open('output.txt', 'w') as file:
    # Write some text to the file
    for book in ISBNS:
        idx = random.sample(indices, k=random.choice(range(1, 7))) # Choose between 1 and 6 categories for each book
        sett=set()
        for i in idx:
            s = "('" + book + "', " + i + "),\n"
            sett.add(s)

        for entry in sett:
            file.write(entry) 