DELIMITER $$

CREATE EVENT delete_old_reservations
ON SCHEDULE EVERY 1 DAY
DO
  DELETE FROM reservation
  WHERE end_date < NOW()

$$

DELIMITER ;