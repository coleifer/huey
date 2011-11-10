import datetime
import unittest

from huey.decorators import crontab


class SkewCrontabTestCase(unittest.TestCase):
    def test_crontab_month(self):
        # validates the following months, 1, 4, 7, 8, 9
        valids = [1, 4, 7, 8, 9]
        validate_m = crontab(month='1,4,*/6,8-9')
        
        for x in xrange(1, 13):
            res = validate_m(datetime.datetime(2011, x, 1))
            self.assertEqual(res, x in valids)
    
    def test_crontab_day(self):
        # validates the following days
        valids = [1, 4, 7, 8, 9, 13, 19, 25, 31]
        validate_d = crontab(day='*/6,1,4,8-9')
        
        for x in xrange(1, 32):
            res = validate_d(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_hour(self):
        # validates the following hours
        valids = [0, 1, 4, 6, 8, 9, 12, 18]
        validate_h = crontab(hour='8-9,*/6,1,4')
        
        for x in xrange(24):
            res = validate_h(datetime.datetime(2011, 1, 1, x))
            self.assertEqual(res, x in valids)
        
        edge = crontab(hour=0)
        self.assertTrue(edge(datetime.datetime(2011, 1, 1, 0, 0)))
        self.assertFalse(edge(datetime.datetime(2011, 1, 1, 12, 0)))
    
    def test_crontab_minute(self):
        # validates the following minutes
        valids = [0, 1, 4, 6, 8, 9, 12, 18, 24, 30, 36, 42, 48, 54]
        validate_m = crontab(minute='4,8-9,*/6,1')
        
        for x in xrange(60):
            res = validate_m(datetime.datetime(2011, 1, 1, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_day_of_week(self):
        # validates the following days of week
        # jan, 1, 2011 is a saturday
        valids = [2, 4, 9, 11, 16, 18, 23, 25, 30]
        validate_dow = crontab(day_of_week='0,2')
        
        for x in xrange(1, 32):
            res = validate_dow(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_all_together(self):
        # jan 1, 2011 is a saturday
        # may 1, 2011 is a sunday
        validate = crontab(
            month='1,5',
            day='1,4,7',
            day_of_week='0,6',
            hour='*/4',
            minute='1-5,10-15,50'
        )
        
        self.assertTrue(validate(datetime.datetime(2011, 5, 1, 4, 11)))
        self.assertTrue(validate(datetime.datetime(2011, 5, 7, 20, 50)))
        self.assertTrue(validate(datetime.datetime(2011, 1, 1, 0, 1)))
        
        # fails validation on month
        self.assertFalse(validate(datetime.datetime(2011, 6, 4, 4, 11)))
        
        # fails validation on day
        self.assertFalse(validate(datetime.datetime(2011, 1, 6, 4, 11)))
        
        # fails validation on day_of_week
        self.assertFalse(validate(datetime.datetime(2011, 1, 4, 4, 11)))
        
        # fails validation on hour
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 1, 11)))
        
        # fails validation on minute
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 4, 6)))
