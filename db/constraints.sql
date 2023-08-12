ALTER TABLE school ADD CONSTRAINT unique_school_name UNIQUE (school_name);
ALTER TABLE school ADD CONSTRAINT unique_phone UNIQUE (phone);

ALTER TABLE book ADD CONSTRAINT pages_positive CHECK(pages > 0);
ALTER TABLE book ADD CONSTRAINT chk_ISBN CHECK (LENGTH(ISBN) = 13 AND ISBN REGEXP '^[0-9]+$');

ALTER TABLE category ADD CONSTRAINT unique_category UNIQUE (category);

ALTER TABLE author ADD CONSTRAINT unique_author UNIQUE (first_name, last_name);

ALTER TABLE borrow ADD CONSTRAINT check_borrow_date CHECK(begin_date < end_date);

ALTER TABLE reservation ADD CONSTRAINT check_reservation_date CHECK(begin_date < end_date);

ALTER TABLE user ADD CONSTRAINT user_unique_email UNIQUE (email);
ALTER TABLE user ADD CONSTRAINT user_unique_username UNIQUE (username);
--create problem with backup/restore
--ALTER TABLE user ADD CONSTRAINT user_school_not_null CHECK(user_type = 'ADMIN' OR school_id IS NOT NULL); 
ALTER TABLE user ADD CONSTRAINT user_email_not_null CHECK(user_type = 'ADMIN' OR email IS NOT NULL);

ALTER TABLE request ADD CONSTRAINT request_unique_email UNIQUE (email);

ALTER TABLE review ADD CONSTRAINT check_rating CHECK(rating >= 1 AND rating <=5);