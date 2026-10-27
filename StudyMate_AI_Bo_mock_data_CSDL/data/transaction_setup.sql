-- Separate test dataset for the transaction tutorial
CREATE TABLE TaiKhoan (MaTK VARCHAR(1) PRIMARY KEY,
 SoDu NUMERIC(12,2) NOT NULL CHECK (SoDu >= 0));
INSERT INTO TaiKhoan VALUES ('A',1000),('B',500);
