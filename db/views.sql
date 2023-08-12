CREATE VIEW school_book AS
SELECT b.ISBN, s.school_id, COUNT(i.ISBN) as total_copies, COUNT(i.ISBN)-COUNT(br.borrow_id) as available_copies
FROM (SELECT ISBN FROM book) b
CROSS JOIN (SELECT school_id FROM school) s
LEFT JOIN item i ON i.ISBN = b.ISBN AND s.school_id = i.school_id
LEFT JOIN (SELECT * FROM borrow WHERE return_date IS NULL) br ON br.item_id = i.item_id 
GROUP BY b.ISBN, s.school_id;
