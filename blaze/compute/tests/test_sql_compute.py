from __future__ import absolute_import, division, print_function

import re
import pytest
from blaze.compute.sql import (compute, computefull, select, lower_column,
        compute_up)
from blaze.expr import *
import sqlalchemy
import sqlalchemy as sa
from blaze.compatibility import xfail
from blaze.utils import unique
from pandas import DataFrame
from blaze import into

t = symbol('t', 'var * {name: string, amount: int, id: int}')

metadata = sa.MetaData()

s = sa.Table('accounts', metadata,
             sa.Column('name', sa.String),
             sa.Column('amount', sa.Integer),
             sa.Column('id', sa.Integer, primary_key=True),
             )

tbig = symbol('tbig', 'var * {name: string, sex: string[1], amount: int, id: int}')

sbig = sa.Table('accountsbig', metadata,
             sa.Column('name', sa.String),
             sa.Column('sex', sa.String),
             sa.Column('amount', sa.Integer),
             sa.Column('id', sa.Integer, primary_key=True),
             )

def normalize(s):
    s2 = ' '.join(s.strip().split()).lower().replace('_', '')
    s3 = re.sub('alias\d*', 'alias', s2)
    return s3


def test_table():
    result = str(computefull(t, s))
    expected = """
    SELECT accounts.name, accounts.amount, accounts.id
    FROM accounts
    """.strip()

    assert normalize(result) == normalize(expected)


def test_projection():
    print(compute(t[['name', 'amount']], s))
    assert str(compute(t[['name', 'amount']], s)) == \
            str(sa.select([s.c.name, s.c.amount]))


def test_eq():
    assert str(compute(t['amount'] == 100, s)) == str(s.c.amount == 100)


def test_eq_unicode():
    assert str(compute(t['name'] == u'Alice', s)) == str(s.c.name == u'Alice')


def test_selection():
    assert str(compute(t[t['amount'] == 0], s)) == \
            str(sa.select([s]).where(s.c.amount == 0))
    assert str(compute(t[t['amount'] > 150], s)) == \
            str(sa.select([s]).where(s.c.amount > 150))


def test_arithmetic():
    assert str(computefull(t['amount'] + t['id'], s)) == \
            str(sa.select([s.c.amount + s.c.id]))
    assert str(compute(t['amount'] + t['id'], s)) == str(s.c.amount + s.c.id)
    assert str(compute(t['amount'] * t['id'], s)) == str(s.c.amount * s.c.id)

    assert str(compute(t['amount'] * 2, s)) == str(s.c.amount * 2)
    assert str(compute(2 * t['amount'], s)) == str(2 * s.c.amount)

    assert (str(compute(~(t['amount'] > 10), s)) ==
            "~(accounts.amount > :amount_1)")

    assert str(computefull(t['amount'] + t['id'] * 2, s)) == \
            str(sa.select([s.c.amount + s.c.id * 2]))

def test_join():
    metadata = sa.MetaData()
    lhs = sa.Table('amounts', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('amount', sa.Integer))

    rhs = sa.Table('ids', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('id', sa.Integer))

    expected = lhs.join(rhs, lhs.c.name == rhs.c.name)
    expected = select(list(unique(expected.columns, key=lambda c:
        c.name))).select_from(expected)

    L = symbol('L', 'var * {name: string, amount: int}')
    R = symbol('R', 'var * {name: string, id: int}')
    joined = join(L, R, 'name')

    result = compute(joined, {L: lhs, R: rhs})

    assert normalize(str(result)) == normalize("""
    SELECT amounts.name, amounts.amount, ids.id
    FROM amounts JOIN ids ON amounts.name = ids.name""")

    assert str(select(result)) == str(select(expected))

    # Schemas match
    assert list(result.c.keys()) == list(joined.fields)

    # test sort on join

    result = compute(joined.sort('amount'), {L: lhs, R: rhs})
    assert normalize(str(result)) == normalize("""
    SELECT amounts.name, amounts.amount, ids.id
    FROM amounts JOIN ids ON amounts.name = ids.name
    ORDER BY amounts.amount""")



def test_clean_complex_join():
    metadata = sa.MetaData()
    lhs = sa.Table('amounts', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('amount', sa.Integer))

    rhs = sa.Table('ids', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('id', sa.Integer))

    L = symbol('L', 'var * {name: string, amount: int}')
    R = symbol('R', 'var * {name: string, id: int}')

    joined = join(L[L.amount > 0], R, 'name')

    result = compute(joined, {L: lhs, R: rhs})


    assert (normalize(str(result)) == normalize("""
    SELECT amounts.name, amounts.amount, ids.id
    FROM amounts JOIN ids ON amounts.name = ids.name
    WHERE amounts.amount > :amount_1""")

    or

    normalize(str(result)) == normalize("""
    SELECT amounts.name, amounts.amount, ids.id
    FROM amounts, (SELECT amounts.name AS name, amounts.amount AS amount
    FROM amounts
    WHERE amounts.amount > :amount_1) JOIN ids ON amounts.name = ids.name"""))




def test_multi_column_join():
    metadata = sa.MetaData()
    lhs = sa.Table('aaa', metadata,
                   sa.Column('x', sa.Integer),
                   sa.Column('y', sa.Integer),
                   sa.Column('z', sa.Integer))

    rhs = sa.Table('bbb', metadata,
                   sa.Column('w', sa.Integer),
                   sa.Column('x', sa.Integer),
                   sa.Column('y', sa.Integer))

    L = symbol('L', 'var * {x: int, y: int, z: int}')
    R = symbol('R', 'var * {w: int, x: int, y: int}')
    joined = join(L, R, ['x', 'y'])

    expected = lhs.join(rhs, (lhs.c.x == rhs.c.x)
                           & (lhs.c.y == rhs.c.y))
    expected = select(list(unique(expected.columns, key=lambda c:
        c.name))).select_from(expected)

    result = compute(joined, {L: lhs, R: rhs})

    assert str(result) == str(expected)

    assert str(select(result)) == str(select(expected))

    # Schemas match
    print(result.c.keys())
    print(joined.fields)
    assert list(result.c.keys()) == list(joined.fields)


def test_unary_op():
    assert str(compute(exp(t['amount']), s)) == str(sa.func.exp(s.c.amount))


def test_unary_op():
    assert str(compute(-t['amount'], s)) == str(-s.c.amount)


def test_reductions():
    assert str(compute(sum(t['amount']), s)) == \
            str(sa.sql.functions.sum(s.c.amount))
    assert str(compute(mean(t['amount']), s)) == \
            str(sa.sql.func.avg(s.c.amount))
    assert str(compute(count(t['amount']), s)) == \
            str(sa.sql.func.count(s.c.amount))

    assert 'amount_sum' == compute(sum(t['amount']), s).name


def test_nelements():
    rhs = str(s.count())
    assert str(compute(t.nelements(), s)) == rhs
    assert str(compute(t.nelements(axis=None), s)) == rhs
    assert str(compute(t.nelements(axis=0), s)) == rhs
    assert str(compute(t.nelements(axis=(0,)), s)) == rhs


def test_nelements_subexpr():
    rhs = str(sa.select([s.c.id, s.c.amount]).count())
    lhs = str(compute(t[['id', 'amount']].nelements(), s))
    assert lhs == rhs


@pytest.mark.xfail(raises=Exception, reason="We don't support axis=1 for"
                   " Record datashapes")
def test_nelements_axis_1():
    assert compute(nelements(t, axis=1), s) == len(s.columns)


def test_count_on_table():
    result = select(compute(t.count(), s))
    assert normalize(str(result)) == normalize("""
    SELECT count(accounts.id) as count_1
    FROM accounts""")

    result = select(compute(t[t.amount > 0].count(), s))
    assert (
        normalize(str(result)) == normalize("""
        SELECT count(accounts.id) as count_1
        FROM accounts
        WHERE accounts.amount > :amount_1""")

        or

        normalize(str(result)) == normalize("""
        SELECT count(id) as count
        FROM (SELECT accounts.name AS name, accounts.amount AS amount, accounts.id AS id
              FROM accounts
              WHERE accounts.amount > :amount_1)"""))

def test_distinct():
    result = str(compute(Distinct(t['amount']), s))

    assert 'distinct' in result.lower()
    assert 'amount' in result.lower()

    print(result)
    assert result == str(sa.distinct(s.c.amount))


def test_distinct_multiple_columns():
    assert normalize(str(compute(t.distinct(), s))) == normalize("""
    SELECT DISTINCT accounts.name, accounts.amount, accounts.id
    FROM accounts""")


def test_nunique():
    result = str(computefull(nunique(t['amount']), s))

    print(result)
    assert 'distinct' in result.lower()
    assert 'count' in result.lower()
    assert 'amount' in result.lower()


@xfail(reason="Fails because SQLAlchemy doesn't seem to know binary reductions")
def test_binary_reductions():
    assert str(compute(any(t['amount'] > 150), s)) == \
            str(sqlalchemy.sql.functions.any(s.c.amount > 150))


def test_by():
    expr = by(t['name'], total=t['amount'].sum())
    result = compute(expr, s)
    expected = sa.select([s.c.name,
                          sa.sql.functions.sum(s.c.amount).label('total')]
                         ).group_by(s.c.name)

    assert str(result) == str(expected)


def test_by_head():
    t2 = t.head(100)
    expr = by(t2['name'], total=t2['amount'].sum())
    result = compute(expr, s)
    # s2 = select(s).limit(100)
    # expected = sa.select([s2.c.name,
    #                       sa.sql.functions.sum(s2.c.amount).label('amount_sum')]
    #                      ).group_by(s2.c.name)
    expected = """
    SELECT alias.name, sum(alias.amount) as total
    FROM (SELECT accounts.name AS name, accounts.amount AS amount, accounts.id AS ID
          FROM accounts
          LIMIT :param_1) as alias
    GROUP BY alias.name"""

    expected = """
    SELECT accounts.name, sum(accounts.amount) as total
    FROM accounts
    GROUP by accounts.name
    LIMIT :param_1"""

    assert normalize(str(result)) == normalize(str(expected))


def test_by_two():
    expr = by(tbig[['name', 'sex']], total=tbig['amount'].sum())
    result = compute(expr, sbig)
    expected = (sa.select([sbig.c.name,
                           sbig.c.sex,
                           sa.sql.functions.sum(sbig.c.amount).label('total')])
                        .group_by(sbig.c.name, sbig.c.sex))

    assert str(result) == str(expected)


def test_by_three():
    result = compute(by(tbig[['name', 'sex']],
                        total=(tbig['id'] + tbig['amount']).sum()),
                     sbig)

    assert normalize(str(result)) == normalize("""
    SELECT accountsbig.name,
           accountsbig.sex,
           sum(accountsbig.id + accountsbig.amount) AS total
    FROM accountsbig GROUP BY accountsbig.name, accountsbig.sex
    """)

def test_by_summary_clean():
    expr = by(t.name, min=t.amount.min(), max=t.amount.max())
    result = compute(expr, s)

    expected = """
    SELECT accounts.name, max(accounts.amount) AS max, min(accounts.amount) AS min
    FROM accounts
    GROUP BY accounts.name
    """

    assert normalize(str(result)) == normalize(expected)


def test_by_summary_single_column():
    expr = by(t.name, n=t.name.count(), biggest=t.name.max())
    result = compute(expr, s)

    expected = """
    SELECT accounts.name, max(accounts.name) AS biggest, count(accounts.name) AS n
    FROM accounts
    GROUP BY accounts.name
    """

    assert normalize(str(result)) == normalize(expected)



def test_join_projection():
    metadata = sa.MetaData()
    lhs = sa.Table('amounts', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('amount', sa.Integer))

    rhs = sa.Table('ids', metadata,
                   sa.Column('name', sa.String),
                   sa.Column('id', sa.Integer))

    L = symbol('L', 'var * {name: string, amount: int}')
    R = symbol('R', 'var * {name: string, id: int}')
    want = join(L, R, 'name')[['amount', 'id']]

    result = compute(want, {L: lhs, R: rhs})
    print(result)
    assert 'join' in str(result).lower()
    assert result.c.keys() == ['amount', 'id']
    assert 'amounts.name = ids.name' in str(result)


def test_sort():
    assert str(compute(t.sort('amount'), s)) == \
            str(select(s).order_by(s.c.amount))

    assert str(compute(t.sort('amount', ascending=False), s)) == \
            str(select(s).order_by(sqlalchemy.desc(s.c.amount)))


def test_sort_on_distinct():
    assert normalize(str(compute(t.amount.sort(), s))) == normalize("""
            SELECT accounts.amount
            FROM accounts
            ORDER BY accounts.amount""")

    assert normalize(str(compute(t.amount.distinct().sort(), s))) == normalize("""
            SELECT DISTINCT accounts.amount as amount
            FROM accounts
            ORDER BY amount""")



def test_head():
    assert str(compute(t.head(2), s)) == str(select(s).limit(2))


def test_label():
    assert str(compute((t['amount'] * 10).label('foo'), s)) == \
            str((s.c.amount * 10).label('foo'))


def test_relabel():
    result = compute(t.relabel({'name': 'NAME', 'id': 'ID'}), s)
    expected = select([s.c.name.label('NAME'), s.c.amount, s.c.id.label('ID')])

    assert str(result) == str(expected)


def test_merge():
    col = (t['amount'] * 2).label('new')

    expr = merge(t['name'], col)

    result = str(compute(expr, s))

    assert 'amount * ' in result
    assert 'FROM accounts' in result
    assert 'SELECT accounts.name' in result
    assert 'new' in result

def test_projection_of_selection():
    print(compute(t[t['amount'] < 0][['name', 'amount']], s))
    assert len(str(compute(t[t['amount'] < 0], s))) > \
            len(str(compute(t[t['amount'] < 0][['name', 'amount']], s)))


def test_outer_join():
    L = symbol('L', 'var * {id: int, name: string, amount: real}')
    R = symbol('R', 'var * {city: string, id: int}')

    from blaze.sql import SQL
    engine = sa.create_engine('sqlite:///:memory:')

    _left = [(1, 'Alice', 100),
            (2, 'Bob', 200),
            (4, 'Dennis', 400)]
    left = SQL(engine, 'left', schema=L.schema)
    left.extend(_left)

    _right = [('NYC', 1),
             ('Boston', 1),
             ('LA', 3),
             ('Moscow', 4)]
    right = SQL(engine, 'right', schema=R.schema)
    right.extend(_right)

    conn = engine.connect()


    query = compute(join(L, R, how='inner'), {L: left.table, R: right.table})
    result = list(map(tuple, conn.execute(query).fetchall()))

    assert set(result) == set(
            [(1, 'Alice', 100, 'NYC'),
             (1, 'Alice', 100, 'Boston'),
             (4, 'Dennis', 400, 'Moscow')])

    query = compute(join(L, R, how='left'), {L: left.table, R: right.table})
    result = list(map(tuple, conn.execute(query).fetchall()))

    assert set(result) == set(
            [(1, 'Alice', 100, 'NYC'),
             (1, 'Alice', 100, 'Boston'),
             (2, 'Bob', 200, None),
             (4, 'Dennis', 400, 'Moscow')])

    query = compute(join(L, R, how='right'), {L: left.table, R: right.table})
    print(query)
    result = list(map(tuple, conn.execute(query).fetchall()))
    print(result)

    assert set(result) == set(
            [(1, 'Alice', 100, 'NYC'),
             (1, 'Alice', 100, 'Boston'),
             (3, None, None, 'LA'),
             (4, 'Dennis', 400, 'Moscow')])

    # SQLAlchemy doesn't support full outer join
    """
    query = compute(join(L, R, how='outer'), {L: left.table, R: right.table})
    result = list(map(tuple, conn.execute(query).fetchall()))

    assert set(result) == set(
            [(1, 'Alice', 100, 'NYC'),
             (1, 'Alice', 100, 'Boston'),
             (2, 'Bob', 200, None),
             (3, None, None, 'LA'),
             (4, 'Dennis', 400, 'Moscow')])
    """

    conn.close()


def test_summary():
    expr = summary(a=t.amount.sum(), b=t.id.count())
    result = str(compute(expr, s))

    assert 'sum(accounts.amount) as a' in result.lower()
    assert 'count(accounts.id) as b' in result.lower()


def test_summary_clean():
    t2 = t[t.amount > 0]
    expr = summary(a=t2.amount.sum(), b=t2.id.count())
    result = str(compute(expr, s))

    assert normalize(result) == normalize("""
    SELECT sum(accounts.amount) as a, count(accounts.id) as b
    FROM accounts
    WHERE accounts.amount > :amount_1""")


def test_summary_by():
    expr = by(t.name, summary(a=t.amount.sum(), b=t.id.count()))

    result = str(compute(expr, s))

    assert 'sum(accounts.amount) as a' in result.lower()
    assert 'count(accounts.id) as b' in result.lower()

    assert 'group by accounts.name' in result.lower()


def test_clean_join():
    metadata = sa.MetaData()
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    city = sa.Table('place', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )
    friends = sa.Table('friends', metadata,
             sa.Column('a', sa.Integer),
             sa.Column('b', sa.Integer),
             )

    tcity = symbol('city', discover(city))
    tfriends = symbol('friends', discover(friends))
    tname = symbol('name', discover(name))

    ns = {tname: name, tfriends: friends, tcity: city}

    expr = join(tfriends, tname, 'a', 'id')
    assert normalize(str(compute(expr, ns))) == normalize("""
    SELECT friends.a, friends.b, name.name
    FROM friends JOIN name on friends.a = name.id""")


    expr = join(join(tfriends, tname, 'a', 'id'), tcity, 'a', 'id')
    assert normalize(str(compute(expr, ns))) == normalize("""
    SELECT friends.a, friends.b, name.name, place.city, place.country
    FROM friends
        JOIN name ON friends.a = name.id
        JOIN place ON friends.a = place.id
        """)



def test_like():
    expr = t.like(name='Alice*')
    assert normalize(str(compute(expr, s))) == normalize("""
    SELECT accounts.name, accounts.amount, accounts.id
    FROM accounts
    WHERE accounts.name LIKE :name_1""")

def test_columnwise_on_complex_selection():
    assert normalize(str(select(compute(t[t.amount > 0].amount + 1, s)))) == \
            normalize("""
    SELECT accounts.amount + :amount_1 AS anon_1
    FROM accounts
    WHERE accounts.amount > :amount_2
    """)

def test_reductions_on_complex_selections():

    assert normalize(str(select(compute(t[t.amount > 0].id.sum(), s)))) == \
            normalize("""
    SELECT sum(accounts.id) as id_sum
    FROM accounts
    WHERE accounts.amount > :amount_1 """)


def test_clean_summary_by_where():
    t2 = t[t.id ==1]
    expr = by(t2.name, sum=t2.amount.sum(), count=t2.amount.count())
    result = compute(expr, s)

    assert normalize(str(result)) == normalize("""
    SELECT accounts.name, count(accounts.amount) AS count, sum(accounts.amount) AS sum
    FROM accounts
    WHERE accounts.id = :id_1
    GROUP BY accounts.name
    """)


def test_by_on_count():
    expr = by(t.name, count=t.count())
    result = compute(expr, s)

    assert normalize(str(result)) == normalize("""
    SELECT accounts.name, count(accounts.id) AS count
    FROM accounts
    GROUP BY accounts.name
    """)


def test_join_complex_clean():
    metadata = sa.MetaData()
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    city = sa.Table('place', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )

    sel = select(name).where(name.c.id > 10)

    tname = symbol('name', discover(name))
    tcity = symbol('city', discover(city))

    ns = {tname: name, tcity: city}

    expr = join(tname[tname.id > 0], tcity, 'id')
    result = compute(expr, ns)

    assert normalize(str(result)) == normalize("""
    SELECT name.id, name.name, place.city, place.country
    FROM name JOIN place ON name.id = place.id
    WHERE name.id > :id_1""")


def test_projection_of_join():
    metadata = sa.MetaData()
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    city = sa.Table('place', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )

    tname = symbol('name', discover(name))
    tcity = symbol('city', discover(city))

    expr = join(tname, tcity[tcity.city == 'NYC'], 'id')[['country', 'name']]

    ns = {tname: name, tcity: city}

    assert normalize(str(compute(expr, ns))) == normalize("""
    SELECT place.country, name.name
    FROM name JOIN place ON name.id = place.id
    WHERE place.city = :city_1""")


def test_lower_column():
    metadata = sa.MetaData()
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    city = sa.Table('place', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )

    tname = symbol('name', discover(name))
    tcity = symbol('city', discover(city))

    ns = {tname: name, tcity: city}

    assert lower_column(name.c.id) is name.c.id
    assert lower_column(select(name).c.id) is name.c.id

    j = name.join(city, name.c.id == city.c.id)
    col = [c for c in j.columns if c.name == 'country'][0]

    assert lower_column(col) is city.c.country


def test_selection_of_join():
    metadata = sa.MetaData()
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    city = sa.Table('place', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )

    tname = symbol('name', discover(name))
    tcity = symbol('city', discover(city))

    ns = {tname: name, tcity: city}

    j = join(tname, tcity, 'id')
    expr = j[j.city == 'NYC'].name
    result = compute(expr, ns)

    assert normalize(str(result)) == normalize("""
    SELECT name.name
    FROM name JOIN place ON name.id = place.id
    WHERE place.city = :city_1""")


def test_join_on_same_table():
    metadata = sa.MetaData()
    T = sa.Table('tab', metadata,
             sa.Column('a', sa.Integer),
             sa.Column('b', sa.Integer),
             )

    t = symbol('tab', discover(T))
    expr = join(t, t, 'a')

    result = compute(expr, {t: T})

    assert normalize(str(result)) == normalize("""
    SELECT tab_left.a, tab_left.b, tab_right.b
    FROM tab AS tab_left JOIN tab AS tab_right
    ON tab_left.a = tab_right.a
    """)

    expr = join(t, t, 'a').b_left.sum()

    result = compute(expr, {t: T})

    assert normalize(str(result)) == normalize("""
    SELECT sum(tab_left.b) as b_left_sum
    FROM tab AS tab_left JOIN tab AS tab_right
    ON tab_left.a = tab_right.a
    """)

    expr = join(t, t, 'a')
    expr = summary(total=expr.a.sum(), smallest=expr.b_right.min())

    result = compute(expr, {t: T})

    assert normalize(str(result)) == normalize("""
    SELECT min(tab_right.b) as smallest, sum(tab_left.a) as total
    FROM tab AS tab_left JOIN tab AS tab_right
    ON tab_left.a = tab_right.a
    """)


def test_field_access_on_engines():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData(engine)
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    name.create()

    city = sa.Table('city', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('city', sa.String),
             sa.Column('country', sa.String),
             )
    city.create()

    s = symbol('s', discover(engine))
    result = compute_up(s.city, engine)
    assert isinstance(result, sa.Table)
    assert result.name == 'city'


def test_computation_directly_on_sqlalchemy_Tables():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData(engine)
    name = sa.Table('name', metadata,
             sa.Column('id', sa.Integer),
             sa.Column('name', sa.String),
             )
    name.create()

    s = symbol('s', discover(name))
    result = compute(s.id + 1, name)
    assert not isinstance(result, sa.sql.Selectable)
    assert list(result) == []


sql_bank = sa.Table('bank', sa.MetaData(),
                 sa.Column('id', sa.Integer),
                 sa.Column('name', sa.String),
                 sa.Column('amount', sa.Integer))
sql_cities = sa.Table('cities', sa.MetaData(),
                   sa.Column('name', sa.String),
                   sa.Column('city', sa.String))

bank = Symbol('bank', discover(sql_bank))
cities = Symbol('cities', discover(sql_cities))


def test_aliased_views_with_two_group_bys():
    expr = by(bank.name, total=bank.amount.sum())
    expr2 = by(expr.total, count=expr.name.count())

    result = compute(expr2, {bank: sql_bank, cities: sql_cities})

    assert normalize(str(result)) == normalize("""
    SELECT alias.total, count(alias.name) as count
    FROM (SELECT bank.name AS name, sum(bank.amount) AS total
          FROM bank
          GROUP BY bank.name) as alias
    GROUP BY alias.total
    """)



def test_aliased_views_with_join():
    joined = join(bank, cities)
    expr = by(joined.city, total=joined.amount.sum())
    expr2 = by(expr.total, count=expr.city.nunique())

    result = compute(expr2, {bank: sql_bank, cities: sql_cities})

    assert normalize(str(result)) == normalize("""
    SELECT alias.total, count(DISTINCT alias.city) AS count
    FROM (SELECT cities.city AS city, sum(bank.amount) AS total
          FROM bank
          JOIN cities ON bank.name = cities.name
          GROUP BY cities.city) as alias
    GROUP BY alias.total
    """)


def test_select_field_on_alias():
    result = compute_up(t.amount, select(s).limit(10).alias('foo'))
    assert normalize(str(select(result))) == normalize("""
        SELECT foo.amount
        FROM (SELECT accounts.name AS name, accounts.amount AS amount, accounts.id AS id
              FROM accounts
              LIMIT :param_1) as foo""")


@pytest.mark.xfail(raises=Exception,
        reason="sqlalchemy.join seems to drop unnecessary tables")
def test_join_on_single_column():
    expr = join(cities[['name']], bank)
    result = compute(expr, {bank: sql_bank, cities: sql_cities})

    assert normalize(str(result)) == """
    SELECT bank.id, bank.name, bank.amount
    FROM bank join cities ON bank.name = cities.name"""


    expr = join(bank, cities.name)
    result = compute(expr, {bank: sql_bank, cities: sql_cities})

    assert normalize(str(result)) == """
    SELECT bank.id, bank.name, bank.amount
    FROM bank join cities ON bank.name = cities.name"""


def test_aliased_views_more():
    metadata = sa.MetaData()
    lhs = sa.Table('aaa', metadata,
                   sa.Column('x', sa.Integer),
                   sa.Column('y', sa.Integer),
                   sa.Column('z', sa.Integer))

    rhs = sa.Table('bbb', metadata,
                   sa.Column('w', sa.Integer),
                   sa.Column('x', sa.Integer),
                   sa.Column('y', sa.Integer))

    L = symbol('L', 'var * {x: int, y: int, z: int}')
    R = symbol('R', 'var * {w: int, x: int, y: int}')

    expr = join(by(L.x, y_total=L.y.sum()),
                R)

    result = compute(expr, {L: lhs, R: rhs})

    assert normalize(str(result)) == normalize("""
        SELECT alias.x, alias.y_total, bbb.w, bbb.y
        FROM (SELECT aaa.x as x, sum(aaa.y) as y_total
              FROM aaa
              GROUP BY aaa.x) AS alias
        JOIN bbb ON alias.x = bbb.x """)

    expr2 = by(expr.w, count=expr.x.count(), total2=expr.y_total.sum())

    result2 = compute(expr2, {L: lhs, R: rhs})

    assert (
        normalize(str(result2)) == normalize("""
            SELECT alias_2.w, count(alias_2.x) as count, sum(alias_2.y_total) as total2
            FROM (SELECT alias.x, alias.y_total, bbb.w, bbb.y
                  FROM (SELECT aaa.x as x, sum(aaa.y) as y_total
                        FROM aaa
                        GROUP BY aaa.x) AS alias
                  JOIN bbb ON alias.x = bbb.x) AS alias_2
            GROUP BY alias_2.w""")

        or

        normalize(str(result2)) == normalize("""
            SELECT bbb.w, count(alias.x) as count, sum(alias.y_total) as total2
            FROM (SELECT aaa.x as x, sum(aaa.y) as y_total
                  FROM aaa
                  GROUP BY aaa.x) as alias
              JOIN bbb ON alias.x = bbb.x
            GROUP BY bbb.w"""))


def test_aliased_views_with_computation():
    engine = sa.create_engine('sqlite:///:memory:')

    df_aaa = DataFrame({'x': [1, 2, 3, 2, 3],
                        'y': [2, 1, 2, 3, 1],
                        'z': [3, 3, 3, 1, 2]})
    df_bbb = DataFrame({'w': [1, 2, 3, 2, 3],
                        'x': [2, 1, 2, 3, 1],
                        'y': [3, 3, 3, 1, 2]})

    df_aaa.to_sql('aaa', engine)
    df_bbb.to_sql('bbb', engine)

    metadata = sa.MetaData(engine)
    metadata.reflect()

    sql_aaa = metadata.tables['aaa']
    sql_bbb = metadata.tables['bbb']

    L = Symbol('aaa', discover(df_aaa))
    R = Symbol('bbb', discover(df_bbb))

    expr = join(by(L.x, y_total=L.y.sum()),
                R)
    a = compute(expr, {L: df_aaa, R: df_bbb})
    b = compute(expr, {L: sql_aaa, R: sql_bbb})
    assert into(set, a) == into(set, b)

    expr2 = by(expr.w, count=expr.x.count(), total2=expr.y_total.sum())
    a = compute(expr2, {L: df_aaa, R: df_bbb})
    b = compute(expr2, {L: sql_aaa, R: sql_bbb})
    assert into(set, a) == into(set, b)

    expr3 = by(expr.x, count=expr.y_total.count())
    a = compute(expr3, {L: df_aaa, R: df_bbb})
    b = compute(expr3, {L: sql_aaa, R: sql_bbb})
    assert into(set, a) == into(set, b)

    expr4 = join(expr2, R)
    a = compute(expr4, {L: df_aaa, R: df_bbb})
    b = compute(expr4, {L: sql_aaa, R: sql_bbb})
    assert into(set, a) == into(set, b)

    """ # Takes a while
    expr5 = by(expr4.count, total=(expr4.x + expr4.y).sum())
    a = compute(expr5, {L: df_aaa, R: df_bbb})
    b = compute(expr5, {L: sql_aaa, R: sql_bbb})
    assert into(set, a) == into(set, b)
    """


def test_distinct_count_on_projection():
    expr = t[['amount']].distinct().count()

    result = compute(expr, {t: s})

    assert (
        normalize(str(result)) == normalize("""
        SELECT count(DISTINCT accounts.amount)
        FROM accounts""")

        or

        normalize(str(result)) == normalize("""
        SELECT count(amount) as count
        FROM (SELECT DISTINCT accounts.amount AS amount
              FROM accounts)"""))

    # note that id is the primary key
    expr = t[['amount', 'id']].distinct().count()

    result = compute(expr, {t: s})
    assert normalize(str(result)) == normalize("""
        SELECT count(id) as count
        FROM (SELECT DISTINCT accounts.amount AS amount, accounts.id AS id
              FROM accounts)""")
