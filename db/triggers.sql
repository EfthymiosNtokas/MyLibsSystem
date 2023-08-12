DELIMITER $$
CREATE TRIGGER delete_reserved_book AFTER INSERT ON borrow
FOR EACH ROW 
BEGIN 
    DELETE FROM reservation 
    WHERE user_id = NEW.user_id AND ISBN = (SELECT ISBN FROM item WHERE item_id = NEW.item_id); 
END $$
DELIMITER ;
