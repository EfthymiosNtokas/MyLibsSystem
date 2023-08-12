CREATE INDEX idx_title ON book (title);

CREATE INDEX idx_category ON category (category);

CREATE INDEX idx_author_name ON author (first_name, last_name);

CREATE INDEX idx_item_school_id_ISBN ON item (ISBN, school_id);

CREATE INDEX idx_username ON user(username, user_password);
CREATE INDEX idx_user_name ON user(last_name, first_name);
CREATE INDEX idx_user_school ON user(school_id);

CREATE INDEX idx_request_school_id ON request(is_active, school_id);
CREATE INDEX idx_request_email ON request(email);

CREATE INDEX idx_borrow ON borrow(user_id, item_id);

CREATE INDEX idx_reservation ON reservation(user_id, ISBN);

CREATE INDEX idx_review ON review(ISBN, user_id);