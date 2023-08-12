
drop database if exists myLibs;
create database myLibs;
USE myLibs;


CREATE TABLE school (
  school_id INT NOT NULL AUTO_INCREMENT,
  school_name VARCHAR(45) NOT NULL,
  school_address VARCHAR(45) NOT NULL,
  city VARCHAR(45) NOT NULL, 
  phone VARCHAR(20),
  email VARCHAR(50),
  principal_first_name VARCHAR(45) NOT NULL,
  principal_last_name VARCHAR(45) NOT NULL,
  last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (school_id)
);

CREATE TABLE book (
    ISBN VARCHAR(20) NOT NULL,
    title VARCHAR(80) NOT NULL,
    publisher VARCHAR(80) NOT NULL,
    pages INT NOT NULL,
    summary VARCHAR(2000),
    cover VARCHAR(500),
    book_language VARCHAR(50) NOT NULL,
    keyword VARCHAR (100), 
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ISBN)
);

CREATE TABLE category (
    category_id INT NOT NULL AUTO_INCREMENT,
    category VARCHAR(50) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY(category_id)
);

CREATE TABLE book_category(
    ISBN VARCHAR(20) NOT NULL,
    category_id INT NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ISBN, category_id),
    FOREIGN KEY (ISBN) REFERENCES book(ISBN) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (category_id) REFERENCES category(category_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE author (
    author_id INT NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(45) NOT NULL,
    last_name VARCHAR(45) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY(author_id)
);

CREATE TABLE book_author(
    ISBN VARCHAR(20) NOT NULL,
    author_id INT NOT NULL,
    PRIMARY KEY (ISBN, author_id),
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (ISBN) REFERENCES book(ISBN) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (author_id) REFERENCES author(author_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE item (
    item_id INT NOT NULL AUTO_INCREMENT,
    school_id INT NOT NULL,
    ISBN VARCHAR(20) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id),
    FOREIGN KEY (school_id) REFERENCES school(school_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (ISBN) REFERENCES book(ISBN) ON DELETE RESTRICT ON UPDATE CASCADE
);
------------------------------------------------------------

CREATE TABLE user (
    user_id INT NOT NULL AUTO_INCREMENT,
    email VARCHAR(50) NULL,
    username VARCHAR(50) NOT NULL,
    user_password VARCHAR (20) NOT NULL,
    user_type ENUM('ADMIN', 'MANAGER', 'TEACHER', 'STUDENT') NOT NULL, 
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    date_of_birth DATE NOT NULL,
    school_id INT NULL,
    is_active TINYINT(1) DEFAULT 1 NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    FOREIGN KEY (school_id) REFERENCES school(school_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

------------------------------------------------------------


CREATE TABLE request (
    request_id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    user_password VARCHAR (20) NOT NULL,
    email VARCHAR(50) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    date_of_birth DATE NOT NULL,
    user_type ENUM('MANAGER', 'TEACHER', 'STUDENT') NOT NULL, 
    school_id INT NOT NULL,
    is_active TINYINT(1) DEFAULT 1 NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY(school_id) REFERENCES school(school_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    PRIMARY KEY (request_id)
);

CREATE TABLE borrow ( 
    borrow_id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL, 
    manager_id INT NOT NULL, 
    item_id INT NOT NULL,
    begin_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    return_date TIMESTAMP NULL, 
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (borrow_id),
    FOREIGN KEY (manager_id) REFERENCES user(user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE reservation (
    reservation_id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    ISBN VARCHAR(20) NOT NULL,
    begin_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (reservation_id),
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (ISBN) REFERENCES book(ISBN) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE review (
    review_id INT NOT NULL AUTO_INCREMENT,
    user_id INT,
    ISBN VARCHAR(20) NOT NULL,
    rating INT NOT NULL,
    review_body VARCHAR(3000),
    approved TINYINT(1) DEFAULT 0,
    PRIMARY KEY (review_id),
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (ISBN) REFERENCES book(ISBN) ON DELETE RESTRICT ON UPDATE CASCADE
);