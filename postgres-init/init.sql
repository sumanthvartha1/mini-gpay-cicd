-- This file runs AUTOMATICALLY when PostgreSQL starts for the first time
-- PostgreSQL looks inside /docker-entrypoint-initdb.d and executes every .sql file

-- TABLE 1: users — stores every user's profile and balance
CREATE TABLE users (
    id SERIAL PRIMARY KEY,          -- auto-incrementing ID (1, 2, 3...)
    name VARCHAR(100) NOT NULL,     -- user's full name
    phone VARCHAR(15) UNIQUE NOT NULL, -- phone number (unique — no duplicates allowed)
    balance DECIMAL(10,2) DEFAULT 0.00 -- money in their account (starts at 0)
);

-- TABLE 2: transactions — stores every money transfer
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,                    -- transaction ID
    sender_id INTEGER REFERENCES users(id),   -- who sent money (links to users table)
    receiver_id INTEGER REFERENCES users(id), -- who received money (links to users table)
    amount DECIMAL(10,2) NOT NULL,            -- how much money was sent
    status VARCHAR(20) DEFAULT 'completed',   -- completed, failed, pending
    created_at TIMESTAMP DEFAULT NOW()        -- when the transaction happened
);

-- INSERT sample users so we have data to work with immediately
INSERT INTO users (name, phone, balance) VALUES
    ('Sumanth', '9999999901', 10000.00),
    ('Rahul', '9999999902', 5000.00),
    ('Priya', '9999999903', 7500.00),
    ('Amit', '9999999904', 3000.00);

-- INSERT sample transactions
INSERT INTO transactions (sender_id, receiver_id, amount) VALUES
    (1, 2, 500.00),   -- Sumanth sent 500 to Rahul
    (3, 1, 1000.00),  -- Priya sent 1000 to Sumanth
    (1, 4, 250.00);   -- Sumanth sent 250 to Amit
