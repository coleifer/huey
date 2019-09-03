kt = __kyototycoon__
db = kt.db


function _select_db(inmap)
  if inmap.db then
    db_idx = tonumber(inmap.db) + 1
    inmap.db = nil
    db = kt.dbs[db_idx]
  else
    db = kt.db
  end
  return db
end

-- helper function for hash functions.
function hkv(inmap, outmap, fn)
  local key = inmap.table_key
  if not key then
    kt.log("system", "hash function missing required: 'table_key'")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  inmap.table_key = nil
  local value, xt = db:get(key)
  local value_tbl = {}
  if value then
    value_tbl = kt.mapload(value)
  end
  local new_value, ok = fn(key, value_tbl, inmap, outmap)
  if ok then
    if new_value and not db:set(key, kt.mapdump(new_value), xt) then
      return kt.RVEINTERNAL
    else
      return kt.RVSUCCESS
    end
  else
    return kt.RVELOGIC
  end
end

-- Redis-like HMSET functionality for setting multiple key/value pairs.
-- accepts: { table_key, ... }
-- returns: { num }
function hmset(inmap, outmap)
  local fn = function(k, v, i, o)
    local num = 0
    for key, value in pairs(i) do
      v[key] = value
      num = num + 1
    end
    o.num = num
    return v, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HMGET functionality for getting multiple key/value pairs.
-- accepts: { table_key, k1, k2 ... }
-- returns: { k1=v1, k2=v2, ... }
function hmget(inmap, outmap)
  local fn = function(k, v, i, o)
    for key, value in pairs(i) do
      o[key] = v[key]
    end
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HMDEL functionality for deleting multiple key/value pairs.
-- accepts: { table_key, k1, k2 ... }
-- returns: { num }
function hmdel(inmap, outmap)
  local fn = function(k, v, i, o)
    local num = 0
    for key, value in pairs(i) do
      if v[key] then
        num = num + 1
        v[key] = nil
      end
    end
    o.num = num
    return v, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HGETALL functionality for getting entire contents of hash.
-- accepts: { table_key }
-- returns: { k1=v1, k2=v2, ... }
function hgetall(inmap, outmap)
  local fn = function(k, v, i, o)
    for key, value in pairs(v) do
      o[key] = value
    end
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HSET functionality for setting a single key/value in a hash.
-- accepts: { table_key, key, value }
-- returns: { num }
function hset(inmap, outmap)
  local fn = function(k, v, i, o)
    local key, value = i.key, i.value
    if not key or not value then
      return nil, false
    end
    v[key] = value
    o.num = 1
    return v, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HSET functionality for setting a key/value if key != exist.
-- accepts: { table_key, key, value }
-- returns: { num }
function hsetnx(inmap, outmap)
  local fn = function(k, v, i, o)
    local key, value = i.key, i.value
    if not key or not value then
      return nil, false
    end
    if v[key] ~= nil then
      o.num = 0
      return nil, true
    else
      v[key] = value
      o.num = 1
      return v, true
    end
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HGET functionality for getting a single key/value in a hash.
-- accepts: { table_key, key }
-- returns: { value }
function hget(inmap, outmap)
  local fn = function(k, v, i, o)
    local key = i.key
    if not key then
      return nil, false
    end
    o.value = v[key]
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HDEL functionality for deleting a single key/value in a hash.
-- accepts: { table_key, key }
-- returns: { num }
function hdel(inmap, outmap)
  local fn = function(k, v, i, o)
    local key = i.key
    if not key then
      return nil, false
    end
    if v[key] then
      v[key] = nil
      o.num = 1
    else
      o.num = 0
    end
    return v, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HLEN functionality for determining number of items in a hash.
-- accepts: { table_key }
-- returns: { num }
function hlen(inmap, outmap)
  local fn = function(k, v, i, o)
    local count = 0
    for _ in pairs(v) do
      count = count + 1
    end
    o.num = count
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- Redis-like HCONTAINS functionality for determining if key exists in a hash.
-- accepts: { table_key, key }
-- returns: { num }
function hcontains(inmap, outmap)
  local fn = function(k, v, i, o)
    local key = i.key
    if not key then
      return nil, false
    end
    if v[key] then
      o.num = 1
    else
      o.num = 0
    end
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- HUNPACK - unpack the hash into separate top-level key/value pairs.
-- accepts { table_key, prefix }
-- returns { num }
function hunpack(inmap, outmap)
  local db_idx = inmap.db
  local db = _select_db(inmap)
  inmap.db = db_idx

  local fn = function(k, v, i, o)
    local prefix = i.prefix or (k .. ":")
    local n = 0
    local accum = {}
    for key, value in pairs(v) do
      accum[prefix .. key] = value
      n = n + 1
    end
    if not db:set_bulk(accum) then
      kt.log("system", "could not set bulk keys in hunpack()")
      return kt.RVEINTERNAL
    end
    o.num = n
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- HPACK - pack top-level key/value pairs into a hash.
-- accepts { table_key, start, stop, count }
-- returns { num }
function hpack(inmap, outmap)
  local db_idx = inmap.db
  local db = _select_db(inmap)
  inmap.db = db_idx

  local fn = function(k, v, i, o)
    local stop = i.stop
    local count = 0xffffffff
    if i.count then count = tonumber(i.count) end

    local n = 0
    local cur = db:cursor()
    if i.start then
      cur:jump(i.start)
    else
      cur:jump()
    end

    while count > n do
      local key, value = cur:get(true)
      if not key then break end
      if stop and key >= stop then break end
      v[key] = value
      n = n + 1
    end

    cur:disable()
    o.num = n
    return (n > 0 and v or nil), true
  end
  return hkv(inmap, outmap, fn)
end


-- Helper for hpackkeys and hpackvalues.
function _hpack_helper(inmap, outmap, f)
  local db_idx = inmap.db
  local db = _select_db(inmap)
  inmap.db = db_idx

  local list_key = inmap.key
  if not list_key then
    kt.log("system", "hpacklist function missing 'key'")
    return kt.RVEINVALID
  end

  local fn = function(k, v, i, o)
    local accum = {}
    local n = 0
    for key, value in pairs(v) do
      table.insert(accum, f(key, value))
      n = n + 1
    end
    if n > 0 then
      if not db:set(list_key, kt.arraydump(accum)) then
        kt.log("system", "hpacklist could not set list key")
        return kt.RVEINTERNAL
      end
    end
    o.num = n
    return nil, true
  end
  return hkv(inmap, outmap, fn)
end


-- HPACKKEYS - pack keys into a LIST.
-- accepts { table_key, key }
-- returns { num }
function hpackkeys(inmap, outmap, f)
  return _hpack_helper(inmap, outmap, function(k, v) return k end)
end


-- HPACKVALUES - pack values into a LIST.
-- accepts { table_key, key }
-- returns { num }
function hpackvalues(inmap, outmap, f)
  return _hpack_helper(inmap, outmap, function(k, v) return v end)
end


-- helper function for set functions.
function skv(inmap, outmap, fn)
  local key = inmap.key
  if not key then
    kt.log("system", "set function missing required: 'key'")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  inmap.key = nil
  local value, xt = db:get(key)
  local value_tbl = {}
  if value then
    value_tbl = kt.mapload(value)
  end
  local new_value, ok = fn(key, value_tbl, inmap, outmap)
  if ok then
    if new_value and not db:set(key, kt.mapdump(new_value), xt) then
      return kt.RVEINTERNAL
    else
      return kt.RVSUCCESS
    end
  else
    return kt.RVELOGIC
  end
end


-- Redis-like SADD functionality for adding value/score to set.
-- accepts: { key, _: value1, _: value2... }
-- returns: { num }
function sadd(inmap, outmap)
  local fn = function(k, v, i, o)
    local n = 0
    for _, value in pairs(i) do
      if v[value] == nil then
        v[value] = ""
        n = n + 1
      end
    end
    outmap.num = n
    if n == 0 then
      return nil, true
    else
      return v, true
    end
  end
  return skv(inmap, outmap, fn)
end


-- Redis-like SCARD functionality for determining cardinality of a set.
-- accepts: { key }
-- returns: { num }
function scard(inmap, outmap)
  local fn = function(k, v, i, o)
    local count = 0
    for _ in pairs(v) do
      count = count + 1
    end
    o.num = count
    return nil, true
  end
  return skv(inmap, outmap, fn)
end


-- Redis-like SISMEMBER functionality for determining if value in a set.
-- accepts: { key, value }
-- returns: { num }
function sismember(inmap, outmap)
  local fn = function(k, v, i, o)
    local value = i.value
    if not value then
      return nil, false
    end

    o.num = 0
    if v[value] ~= nil then
      o.num = 1
    end
    return nil, true
  end
  return skv(inmap, outmap, fn)
end


-- Redis-like SMEMBERS functionality for getting all values in a set.
-- accepts: { key }
-- returns: { v1, v2, ... }
function smembers(inmap, outmap)
  local fn = function(k, v, i, o)
    local idx = 0
    for key, value in pairs(v) do
      o[idx] = key
      idx = idx + 1
    end
    return nil, true
  end
  return skv(inmap, outmap, fn)
end


-- Redis-like SPOP functionality for removing a member from a set.
-- accepts: { key }
-- returns: { num, value }
function spop(inmap, outmap)
  local fn = function(k, v, i, o)
    o.num = 0
    for key, value in pairs(v) do
      o.num = 1
      o.value = key
      v[key] = nil
      return v, true
    end
    return nil, true
  end
  return skv(inmap, outmap, fn)
end


-- Redis-like SREM functionality for removing one or more values from a set.
-- accepts: { key, _: value1, _: value2... }
-- returns: { num }
function srem(inmap, outmap)
  local fn = function(k, v, i, o)
    local n = 0
    for _, value in pairs(i) do
      if v[value] ~= nil then
        v[value] = nil
        n = n + 1
      end
    end

    o.num = n
    if n > 0 then
      return v, true
    else
      return nil, true
    end
  end
  return skv(inmap, outmap, fn)
end


-- helper function for set operations on 2 keys.
function svv(inmap, outmap, fn)
  local key1, key2 = inmap.key, inmap.key2
  if not key1 or not key2 then
    kt.log("system", "set function missing required: 'key' or 'key2'")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  local value1, xt = db:get(key1)
  local value2, xt = db:get(key2)

  local value_tbl1 = {}
  local value_tbl2 = {}
  if value1 then value_tbl1 = kt.mapload(value1) end
  if value2 then value_tbl2 = kt.mapload(value2) end

  local ret = fn(value_tbl1, value_tbl2, inmap, outmap)
  if ret == kt.RVSUCCESS and inmap.dest then
    local dest_tbl = {}
    for _, val in pairs(outmap) do
      dest_tbl[val] = ''
    end
    if not db:set(inmap.dest, kt.mapdump(dest_tbl), xt) then
      return kt.RVEINTERNAL
    end
  end
  return kt.RVSUCCESS
end


-- Redis-like SINTER functionality for finding intersection of 2 sets.
-- accepts: { key, key2, (dest) }
-- returns: { ... }
function sinter(inmap, outmap)
  local fn = function(v1, v2, i, o)
    local idx = 0
    for key, val in pairs(v1) do
      if v2[key] ~= nil then
        o[idx] = key
        idx = idx + 1
      end
    end
    return kt.RVSUCCESS
  end
  return svv(inmap, outmap, fn)
end


-- Redis-like SUNION functionality for finding union of 2 sets.
-- accepts: { key, key2, (dest) }
-- returns: { ... }
function sunion(inmap, outmap)
  local fn = function(v1, v2, i, o)
    local idx = 0
    for key, val in pairs(v1) do
      o[idx] = key
      idx = idx + 1
    end
    for key, val in pairs(v2) do
      if v1[key] == nil then
        o[idx] = key
        idx = idx + 1
      end
    end
    return kt.RVSUCCESS
  end
  return svv(inmap, outmap, fn)
end


-- Redis-like SDIFF functionality for finding difference of set1 and set2.
-- accepts: { key, key2, (dest) }
-- returns: { ... }
function sdiff(inmap, outmap)
  local fn = function(v1, v2, i, o)
    local idx = 0
    for key, val in pairs(v1) do
      if v2[key] == nil then
        o[idx] = key
        idx = idx + 1
      end
    end
    return kt.RVSUCCESS
  end
  return svv(inmap, outmap, fn)
end


-- helper function for list functions.
function lkv(inmap, outmap, fn)
  local key = inmap.key
  if not key then
    kt.log("system", "list function missing required: 'key'")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  inmap.key = nil
  local value, xt = db:get(key)
  local value_array = {}
  if value then
    value_array = kt.arrayload(value)
  end
  local new_value, ok = fn(key, value_array, inmap, outmap)
  if ok then
    if new_value and not db:set(key, kt.arraydump(new_value), xt) then
      return kt.RVEINTERNAL
    else
      return kt.RVSUCCESS
    end
  else
    return kt.RVELOGIC
  end
end


-- Redis-like LPUSH
-- accepts: { key, value }
-- returns: { length }
function llpush(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local value = inmap.value
    if not value then
      kt.log("system", "missing value parameter to llpush")
      return nil, false
    end
    table.insert(arr, 1, value)
    outmap.length = #arr
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end

-- Redis-like RPUSH
-- accepts: { key, value }
-- returns: { length }
function lrpush(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local value = inmap.value
    if not value then
      kt.log("system", "missing value parameter to lrpush")
      return nil, false
    end
    table.insert(arr, value)
    outmap.length = #arr
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- Append multiple items to the end of a list.
-- accepts: { key, 0: value1, 1: value2, ... }
-- returns: {}
function lextend(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local i = 0
    while true do
      local value = inmap[tostring(i)]
      if value == nil then
        break
      else
        table.insert(arr, value)
        i = i + 1
      end
    end
    outmap.length = #arr
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


function _normalize_index(array_len, idx)
  local index = tonumber(idx or "0") + 1
  if index < 1 then
    index = array_len + index
    if index < 1 then return nil, false end
  end
  if index > array_len then return nil, false end
  return index, true
end


-- Redis-like LRANGE -- zero-based.
-- accepts: { key, start, stop }
-- returns: { i1, i2, ... }
function lrange(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local arrsize = #arr
    local start = tonumber(inmap.start or "0") + 1
    if start < 1 then
      start = arrsize + start
      if start < 1 then
        return nil, true
      end
    end

    local stop = inmap.stop
    if stop then
      stop = tonumber(stop)
      if stop < 0 then
        stop = arrsize + stop
      end
    else
      stop = arrsize
    end

    local n = 0
    for i = start, stop, 1 do
      outmap[tostring(n)] = arr[i]
      n = n + 1
    end
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- Redis-like LINDEX -- zero-based.
-- accepts: { key, index }
-- returns: { value }
function lindex(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local index, ok = _normalize_index(#arr, inmap.index)
    if ok then
      local val = arr[index]
      outmap.value = arr[index]
    end
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- LINSERT -- zero-based.
-- accepts: { key, index, value }
-- returns: { length }
function linsert(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local index, ok = _normalize_index(#arr, inmap.index)

    -- Overrides to allow insertion at the head or tail of empty lists.
    if not ok and inmap.index then
      local i = tonumber(inmap.index)
      if i == 0 or i == -1 then
        index = 1
        ok = true
      end
    end

    if not ok then
      kt.log("system", "invalid list index in linsert()")
      return nil, true
    end
    if not inmap.value then
      kt.log("info", "missing value for linsert")
      return nil, false
    end
    table.insert(arr, index, inmap.value)
    outmap.length = #arr
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- Redis-like LPOP -- removes first elem.
-- accepts: { key }
-- returns: { value }
function llpop(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    outmap.value = arr[1]
    table.remove(arr, 1)
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- Redis-like RPOP -- removes last elem.
-- accepts: { key }
-- returns: { value }
function lrpop(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    outmap.value = arr[#arr]
    arr[#arr] = nil
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- LREM -- remove an item by index.
-- accepts: { key, index }
-- returns: { value }
function lrem(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local index, ok = _normalize_index(#arr, inmap.index)
    if not ok then
      kt.log("system", "invalid list index in lrem()")
      return nil, true
    end
    outmap.value = arr[index]
    table.remove(arr, index)
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- LREMRANGE -- remove a range of items by index from [start, stop).
-- accepts: { key, start, stop }
-- returns: { length }
function lremrange(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local start = 1
    local stop = #arr
    local ok

    if inmap.start then
      start, ok = _normalize_index(#arr, inmap.start)
      if not ok then
        kt.log("system", "invalid start index in lremrange()")
        return nil, false
      end
    end
    if inmap.stop then
      stop, ok = _normalize_index(#arr, inmap.stop)
      if not ok then
        kt.log("system", "invalid stop index in lremrange()")
        return nil, false
      elseif stop > 0 then
        stop = stop - 1
      end
    end
    if start > stop then start, stop = stop, start end

    for i = stop, start, -1 do
      table.remove(arr, i)
    end
    outmap.length = #arr
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- Redis-like LLEN -- returns length of list.
-- accepts: { key }
-- returns: { num }
function llen(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    outmap.num = #arr
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- Redis-like LSET -- set item at index.
-- accepts: { key, index, value }
-- returns: { num }
function lset(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    local idx = tonumber(inmap.index or "0")
    if not inmap.value then
      kt.log("info", "missing value for lset")
      return nil, false
    end
    if idx < 0 or idx >= #arr then
      kt.log("info", "invalid index for lset")
      return nil, true
    end
    arr[idx + 1] = inmap.value
    outmap['num'] = 1
    return arr, true
  end
  return lkv(inmap, outmap, fn)
end


-- LFIND -- returns index by value.
-- accepts { key, value }
-- returns { index (or -1) }
function lfind(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    outmap.index = -1
    for i, value in ipairs(arr) do
      if value == inmap.value then
        outmap.index = i - 1
        break
      end
    end
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- LRFIND -- returns index by value searching from right-to-left.
-- accepts { key, value }
-- returns { index (or -1) }
function lrfind(inmap, outmap)
  local fn = function(key, arr, inmap, outmap)
    outmap.index = -1
    local i = 0
    for i = #arr, 1, -1 do
      if arr[i] == inmap.value then
        outmap.index = i - 1
        break
      end
    end
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- LUNPACK -- unpack the items of a list into their own keys.
-- accepts { key, prefix, start, stop, format }
-- returns { num }
function lunpack(inmap, outmap)
  local db_idx = inmap.db
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  inmap.db = db_idx  -- Restore DB so it can be read by lkv.

  local fn = function(key, arr, inmap, outmap)
    local prefix = inmap.prefix or (key .. ":")
    local format = inmap.format or "%04d"
    local arrsize = #arr
    local start = tonumber(inmap.start or "0") + 1

    if start < 1 then
      start = arrsize + start
      if start < 1 then
        return nil, true
      end
    end

    local stop = inmap.stop
    if stop then
      stop = tonumber(stop)
      if stop < 0 then
        stop = arrsize + stop
      end
    else
      stop = arrsize
    end

    local k
    local n = 0
    local accum = {}

    for i = start, stop, 1 do
      k = prefix .. string.format(format, n)
      accum[k] = arr[i]
      n = n + 1
    end

    if not db:set_bulk(accum) then
      kt.log("system", "could not set bulk keys in lunpack()")
      return kt.RVEINTERNAL
    end
    outmap.num = n
    return nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- LPACK -- pack a range of values into a list key.
-- accepts { key, start, stop, count }
-- returns { num }
function lpack(inmap, outmap)
  local db_idx = inmap.db
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  inmap.db = db_idx  -- Restore DB so it can be read by lkv.

  local fn = function(key, arr, inmap, outmap)
    local stop = inmap.stop
    local count = 0xffffffff
    if inmap.count then count = tonumber(inmap.count) end

    local n = 0
    local cur = db:cursor()
    if inmap.start then
      cur:jump(inmap.start)
    else
      cur:jump()
    end

    while count > n do
      local key, value = cur:get(true)
      if not key then break end
      if stop and key >= stop then break end
      table.insert(arr, value)
      n = n + 1
    end

    cur:disable()
    outmap.num = n
    return n > 0 and arr or nil, true
  end
  return lkv(inmap, outmap, fn)
end


-- Misc helpers.


-- Move src to dest.
-- accepts: { src, dest }
-- returns: {}
function move(inmap, outmap)
  local src = inmap.src
  local dest = inmap.dest
  if not src or not dest then
    kt.log("info", "missing src and/or dest key in move() call")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  local keys = { src, dest }
  local first = true
  local src_val = nil
  local src_xt = nil
  local function visit(key, value, xt)
    -- Operating on first key, capture value and xt and remove.
    if first then
      src_val = value
      src_xt = xt
      first = false
      return kt.Visitor.REMOVE
    end

    -- Operating on dest key, store value and xt.
    if src_val then
      return src_val, src_xt
    end
    return kt.Visitor.NOP
  end

  if not db:accept_bulk(keys, visit) then
    return kt.RVEINTERNAL
  end

  if not src_val then
    return kt.RVELOGIC
  end
  return kt.RVSUCCESS
end


-- List all key-value pairs.
-- accepts: {}
-- returns: { k=v ... }
function list(inmap, outmap)
  local db = _select_db(inmap) -- Allow db to be specified as argument.
  local function visit(key, value)
    outmap[key] = value
    return kt.Visitor.NOP
  end
  db:iterate(visit, false)
  return kt.RVSUCCESS
end


-- Fetch a range of key-value pairs.
-- accepts: { start: key, stop: key, db: idx }
-- returns: { k1=v1, k2=v2, ... }
function get_range(inmap, outmap)
  local db = _select_db(inmap)
  local start_key = inmap.start
  local stop_key = inmap.stop
  local cur = db:cursor()
  if start_key then
    if not cur:jump(start_key) then
      cur:disable()
      return kt.RVSUCCESS
    end
  else
    if not cur:jump() then
      cur:disable()
      return kt.RVSUCCESS
    end
  end
  local key, value
  while true do
    key = cur:get_key()
    if stop_key and key > stop_key then
      break
    end
    outmap[key] = cur:get_value()
    if not cur:step() then
      break
    end
  end
  cur:disable()
  return kt.RVSUCCESS
end


-- Hash one or more values.
-- accepts: { val1: method1, val2: method2, ... }
-- returns: { val1: hash1, val2: hash2, ... }
function hash(inmap, outmap)
  for key, val in pairs(inmap) do
    if val == 'fnv' then
      outmap[key] = kt.hash_fnv(val)
    else
      outmap[key] = kt.hash_murmur(val)
    end
  end
end


-- Get a portion of a string value stored in a key. Behaves like slice operator
-- does in Python.
-- accepts: { key, start, stop, db }
-- returns: { value }
function get_part(inmap, outmap)
  local db = _select_db(inmap)
  local start_idx = inmap.start or 0
  local stop_idx = inmap.stop
  local key = inmap.key
  if not key then
    kt.log("info", "missing key in get_part() call")
    return kt.RVEINVALID
  end

  local value, xt = db:get(key)
  if value ~= nil then
    start_idx = tonumber(start_idx)
    if start_idx >= 0 then start_idx = start_idx + 1 end
    if stop_idx then
      stop_idx = tonumber(stop_idx)
      -- If the stop index is negative, we need to subtract 1 to get
      -- Python-like semantics.
      if stop_idx < 0 then stop_idx = stop_idx - 1 end
      value = string.sub(value, start_idx, stop_idx)
    else
      value = string.sub(value, start_idx)
    end
  end
  outmap.value = value
  return kt.RVSUCCESS
end


-- Queue helpers.

QUEUE_SPLIT = 500000000000

-- Simple wrapper that does some basic validation and dispatches to the
-- user-defined callback.
function _qfn(inmap, outmap, required, fn)
  local db = _select_db(inmap)
  for i, key in pairs(required) do
    if not inmap[key] then
      kt.log("info", "queue: missing required parameter: " .. key)
      return kt.RVEINVALID
    end
  end
  return fn(db, inmap, outmap)
end


-- add/enqueue data to a queue
-- accepts: { queue, data, score, db }
-- returns { id }
function queue_add(inmap, outmap)
  local fn = function(db, i, o)
    local score = QUEUE_SPLIT - (tonumber(i.score) or 0)
    local id = db:increment_double(i.queue, 1)
    if not id then
      kt.log("info", "unable to determine id when adding item to queue!")
      return kt.RVELOGIC
    end
    local key = string.format("%s\t%012d%012d", i.queue, score, id)
    if not db:add(key, i.data) then
      kt.log("info", "could not add key, already exists")
      return kt.RVELOGIC
    end
    o.id = id
    return kt.RVSUCCESS
  end
  return _qfn(inmap, outmap, {"queue", "data"}, fn)
end


-- add/enqueue multiple items to a queue
-- accepts: { queue, 0: data0, 1: data1, ... n: dataN, score, db }
-- returns { num }
function queue_madd(inmap, outmap)
  local fn = function(db, i, o)
    local score = QUEUE_SPLIT - (tonumber(i.score) or 0)
    local n = 0
    while i[tostring(n)] ~= nil do
      local id = db:increment_double(i.queue, 1)
      if not id then
        kt.log("info", "unable to determine id when adding item to queue!")
        return kt.RVELOGIC
      end
      local key = string.format("%s\t%012d%012d", i.queue, score, id)
      if not db:add(key, i[tostring(n)]) then
        kt.log("info", "could not add key, already exists")
        return kt.RVELOGIC
      end
      n = n + 1
    end
    o.num = n
    return kt.RVSUCCESS
  end
  return _qfn(inmap, outmap, {"queue"}, fn)
end


function _queue_iter(db, queue, n, callback)
  -- Perform a forward iteration through the queue (up to "n" items). The
  -- user-defined callback returns a 2-tuple of (ok, incr) to signal that we
  -- should continue looping, and to increment the counter, respectively.
  local num = 0
  local cursor = db:cursor()
  local key = string.format("%s\t", queue)
  local pattern = string.format("^%s\t", queue)

  local score_start = string.len(queue) + 2  -- First byte after "\t".
  local score_end = score_start + 11  -- read 12 bytes.

  -- No data, we're done.
  if not cursor:jump(key) then
    cursor:disable()
    return num
  end

  local k, v, xt, ok, incr

  while n ~= 0 do
    -- Retrieve the key, value and xt from the cursor. If the cursor is
    -- invalidated then nil is returned.
    k, v, xt = cursor:get(false)
    if not k then break end

    -- If this is not a queue item key, we are done.
    if not k:match(pattern) then break end

    -- Extract the score of the item.
    local score = tonumber(string.sub(k, score_start, score_end))

    -- Pass control to the user-defined function, which is responsible for
    -- stepping the cursor.
    ok, incr = callback(cursor, k, v, num, QUEUE_SPLIT - score)
    if not ok then break end

    if incr then
      num = num + 1
      n = n - 1
    end
  end

  cursor:disable()
  return num
end


function _queue_iter_reverse(db, queue, n, callback)
  -- Perform a backward iteration through the queue (up to "n" items). The
  -- user-defined callback returns a 2-tuple of (ok, incr) to signal that we
  -- should continue looping, and to increment the counter, respectively.
  local num = 0
  local cursor = db:cursor()
  local max_key = string.format("%s\t\255", queue)
  local pattern = string.format("^%s\t", queue)

  local score_start = string.len(queue) + 2  -- First byte after "\t".
  local score_end = score_start + 11  -- read 12 bytes.

  -- No data, we're done.
  if not cursor:jump_back(max_key) then
    cursor:disable()
    return num
  end

  local k, v, xt, ok, incr

  while n ~= 0 do
    -- Retrieve the key, value and xt from the cursor. If the cursor is
    -- invalidated then nil is returned.
    k, v, xt = cursor:get(false)
    if not k then break end

    -- If this is a queue item key, we remove the value (which implicitly steps
    -- to the next key).
    if not k:match(pattern) then break end

    -- Extract the score of the item.
    local score = tonumber(string.sub(k, score_start, score_end))

    ok, incr = callback(cursor, k, v, num, QUEUE_SPLIT - score)
    if not ok then break end

    if incr then
      num = num + 1
      n = n - 1
    end
  end

  cursor:disable()
  return num
end


-- Remove items from a queue based on value (up-to "n" items).
-- accepts: { queue, data, db, n, min_score }
-- returns { num }
function queue_remove(inmap, outmap)
  local cb = function(db, i, o)
    local queue = i.queue
    local data = i.data
    local n = tonumber(i.n or -1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, k, v, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step(), false
      end

      if data == v then
        return cursor:remove(), true
      else
        return cursor:step(), false
      end
    end
    outmap.num = _queue_iter(db, queue, n, iter_cb)
    return kt.RVSUCCESS
  end
  return _qfn(inmap, outmap, {"queue", "data"}, cb)
end


-- Remove items from the back of a queue, based on value (up-to "n" items).
-- accepts: { queue, data, db, n, min_score }
-- returns { num }
function queue_rremove(inmap, outmap)
  local cb = function(db, i, o)
    local queue = i.queue
    local data = i.data
    local n = tonumber(i.n or -1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, k, v, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step_back(), false
      end

      if data == v then
        return cursor:remove(), true
      else
        return cursor:step_back(), false
      end
    end
    outmap.num = _queue_iter_reverse(db, queue, n, iter_cb)
    return kt.RVSUCCESS
  end
  return _qfn(inmap, outmap, {"queue", "data"}, cb)
end


-- update score for an item in the queue
-- accepts: { queue, data, db, n, score }
-- returns { num }
function queue_set_score(inmap, outmap)
  local cb = function(db, i, o)
    local queue = i.queue
    local data = i.data
    local n = tonumber(i.n or -1)
    local new_score = tonumber(i.score) or 0
    local new_score_k = QUEUE_SPLIT - new_score
    local id_start = string.len(queue) + 2 + 12
    local id_end = id_start + 11  -- read 12 bytes.
    local accum = {}
    local remove = {}

    local iter_cb = function(cursor, k, v, num, score)
      if data == v and score ~= new_score then
        local item_id = string.sub(k, id_start, id_end)
        accum[string.format("%s\t%012d%012d", queue, new_score_k, item_id)] = v
        table.insert(remove, k)
        return cursor:step(), true
      else
        return cursor:step(), false
      end
    end
    _queue_iter(db, queue, n, iter_cb)
    outmap.num = #remove
    if outmap.num then
      db:remove_bulk(remove)
      db:set_bulk(accum)
    end
    return kt.RVSUCCESS
  end
  return _qfn(inmap, outmap, {"queue", "data", "score"}, cb)
end


-- pop/dequeue data from queue
-- accepts: { queue, n, db, min_score }
-- returns { idx: data, ... }
function queue_pop(inmap, outmap)
  local cb = function(db, i, o)
    local n = tonumber(i.n or 1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, key, value, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step(), false
      end

      o[tostring(num)] = value
      return cursor:remove(), true
    end
    _queue_iter(db, i.queue, n, iter_cb)
  end
  return _qfn(inmap, outmap, {"queue"}, cb)
end


-- pop/dequeue data from end of queue
-- accepts: { queue, n, db, min_score }
-- returns { idx: data, ... }
function queue_rpop(inmap, outmap)
  local cb = function(db, i, o)
    local n = tonumber(i.n or 1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, key, value, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step_back(), false
      end

      o[tostring(num)] = value
      return cursor:remove(), true
    end
    _queue_iter_reverse(db, i.queue, n, iter_cb)
  end
  return _qfn(inmap, outmap, {"queue"}, cb)
end


-- blocking pop from head of queue
-- accepts: { queue, db, timeout, min_score }
-- returns { 0: data } or an empty response on timeout.
function queue_bpop(inmap, outmap)
  local cutoff
  if inmap.timeout then
    local timeout = tonumber(inmap.timeout)
    cutoff = kt.time() + timeout
  end
  local min_score = tonumber(inmap.min_score)

  local cb = function(db, i, o)
    local iter_cb = function(cursor, key, value, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step(), false
      end

      o[tostring(num)] = value
      return cursor:remove(), true
    end
    local t = 0.1
    while _queue_iter(db, i.queue, 1, iter_cb) == 0 do
      if cutoff and kt.time() >= cutoff then break end
      kt.sleep(t)
      t = t * 1.15
      if t > 1 then t = 1 end
    end
  end
  return _qfn(inmap, outmap, {"queue"}, cb)
end


-- peek data from queue
-- accepts: { queue, n, db, min_score }
-- returns { idx: data, ... }
function queue_peek(inmap, outmap)
  local cb = function(db, i, o)
    local n = tonumber(i.n or 1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, key, value, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step(), false
      end

      o[tostring(num)] = value
      return cursor:step(), true
    end
    _queue_iter(db, i.queue, n, iter_cb)
  end
  return _qfn(inmap, outmap, {"queue"}, cb)
end


-- peek data from end of queue
-- accepts: { queue, n, db, min_score }
-- returns { idx: data, ... }
function queue_rpeek(inmap, outmap)
  local cb = function(db, i, o)
    local n = tonumber(i.n or 1)
    local min_score = tonumber(i.min_score)
    local iter_cb = function(cursor, key, value, num, score)
      if min_score ~= nil and score < min_score then
        return cursor:step_back(), false
      end

      o[tostring(num)] = value
      return cursor:step_back(), true
    end
    _queue_iter_reverse(db, i.queue, n, iter_cb)
  end
  return _qfn(inmap, outmap, {"queue"}, cb)
end


-- get queue size
-- accepts: { queue, db }
-- returns: { num }
function queue_size(inmap, outmap)
  if not inmap.queue then
    kt.log("info", "missing queue parameter in queue_size call")
    return kt.RVEINVALID
  end

  local db = _select_db(inmap)
  local keys = db:match_prefix(string.format("%s\t", inmap.queue))
  outmap.num = tostring(#keys)
  return kt.RVSUCCESS
end


-- clear queue, removing all items
-- accepts: { queue, db }
-- returns: { num }
function queue_clear(inmap, outmap)
  if not inmap.queue then
    kt.log("info", "missing queue parameter in queue_size call")
    return kt.RVEINVALID
  end

  local db = _select_db(inmap)
  local keys = db:match_prefix(string.format("%s\t", inmap.queue))
  db:remove_bulk(keys)
  db:remove(inmap.queue)
  outmap.num = tostring(#keys)
  return kt.RVSUCCESS
end


-- Simple hexastore graph.

-- Python-like string split, with proper handling of edge-cases.
function nsplit(s, delim, n)
  n = n or -1
  local pos, length = 1, #s
  local parts = {}
  while pos do
    local dstart, dend = string.find(s, delim, pos, true)
    local part
    if not dstart then
      part = string.sub(s, pos)
      pos = nil
    elseif dend < dstart then
      part = string.sub(s, pos, dstart)
      if dstart < length then
        pos = dstart + 1
      else
        pos = nil
      end
    else
      part = string.sub(s, pos, dstart - 1)
      pos = dend + 1
    end
    table.insert(parts, part)
    n = n - 1
    if n == 0 and pos then
      if dend < length then
        table.insert(parts, string.sub(s, pos))
      end
      break
    end
  end
  return parts
end

function _hx_keys_for_values(s, p, o)
  local perms = {
    {'spo', s, p, o},
    {'pos', p, o, s},
    {'osp', o, s, p}}
  local output = {}
  for i = 1, #perms do
    output[i] = table.concat(perms[i], '::')
  end
  return output
end

function _hx_keys_for_query(s, p, o)
  local parts = {}
  local key = function(parts) return table.concat(parts, '::') end

  if s and p and o then
    return key({"spo", s, p, o}), nil
  elseif s and p then
    parts = {"spo", s, p}
  elseif s and o then
    parts = {"osp", s, o}
  elseif p and o then
    parts = {"pos", p, o}
  elseif s then
    parts = {"spo", s}
  elseif p then
    parts = {"pos", p}
  elseif o then
    parts = {"osp", o}
  end
  local term = {}
  for _, value in pairs(parts) do
    table.insert(term, value)
  end
  table.insert(parts, "")
  table.insert(term, "\255")
  return key(parts), key(term)
end

-- add item to hexastore
-- accepts { s, p, o } (subject, predicate, object)
function hx_add(inmap, outmap)
  local db, s, p, o = _select_db(inmap), inmap.s, inmap.p, inmap.o
  if not s or not p or not o then
    kt.log("info", "missing s/p/o parameter in hx_add call")
    return kt.RVEINVALID
  end

  local data = {}
  for i, key in pairs(_hx_keys_for_values(s, p, o)) do
    data[key] = ""
  end
  db:set_bulk(data)
  return kt.RVSUCCESS
end

-- remove item from hexastore
-- accepts { s, p, o }
function hx_remove(inmap, outmap)
  local db, s, p, o = _select_db(inmap), inmap.s, inmap.p, inmap.o
  if not s or not p or not o then
    kt.log("info", "missing s/p/o parameter in hx_remove call")
    return kt.RVEINVALID
  end

  db:remove_bulk(_hx_keys_for_values(s, p, o))
  return kt.RVSUCCESS
end

-- query hexastore
-- accepts { s, p, o }
function hx_query(inmap, outmap)
  local db, s, p, o = _select_db(inmap), inmap.s, inmap.p, inmap.o
  if not s and not p and not o then
    kt.log("info", "missing s/p/o parameter in hx_query call")
    return kt.RVEINVALID
  end

  local start, stop = _hx_keys_for_query(s, p, o)
  if not stop then
    local value, xt = db:get(start)
    if value then outmap['0'] = value end
    return kt.RVSUCCESS
  end

  local cursor = db:cursor()
  if not cursor:jump(start) then
    cursor:disable()
    return kt.RVSUCCESS
  end

  local i = 0
  local key, value, xt
  while true do
    key, value, xt = cursor:get()
    if key > stop then break end
    _hx_key_to_table(outmap, key, i, s == nil, p == nil, o == nil)
    i = i + 1
    if not cursor:step() then
      break
    end
  end
  cursor:disable()
  return kt.RVSUCCESS
end

function _hx_key_to_table(tbl, key, idx, store_s, store_p, store_o)
  -- internal function for adding the parts of an s/p/o key to a result table.
  -- only stores the parts indicated (based on the user query).
  local parts = nsplit(key, "::")
  local structure = parts[1]  -- e.g., "spo", "ops", "pos".
  local k
  for i = 1, 3 do
    k = string.sub(structure, i, i)  -- e.g., "s", "p" or "o".
    if (k == 'o' and store_o) or (k == 's' and store_s) or (k == 'p' and store_p) then
      tbl[k .. tostring(idx)] = parts[i + 1]
    end
  end
end


-- I use a custom build of Kyoto Tycoon that includes some additional lua
-- libraries as built-ins, including the msgpack serializer from Redis.
if cmsgpack ~= nil then
  -- Assuming a key contains a msgpack-serialized table, this function takes
  -- the key/value pairs in the serialized table and unpacks them into their
  -- own msgpack-serialized keys.
  -- accepts { key }
  -- returns { num }
  function unpack_packed_key(inmap, outmap)
    local key = inmap.key
    if not key then
      kt.log('system', 'unpack_packed_key() missing required "key"')
      return kt.RVEINVALID
    else
      inmap.key = nil
    end
    local db = _select_db(inmap)
    local value, xt = db:get(key)
    local n = 0
    if value ~= nil then
      -- Unpack the msgpack-serialized data into separate keys/values.
      local unpacked = cmsgpack.unpack(value)
      for k, v in pairs(unpacked) do
        if not db:set(k, cmsgpack.pack(v), xt) then
          kt.log('system', 'error setting key in unpack_packed_key()')
          return kt.RVEINTERNAL
        end
        n = n + 1
      end
    end
    outmap.num = n
    return kt.RVSUCCESS
  end

  -- Takes any number of msgpack-serialized keys and packs them into a single
  -- msgpack-serialized key.
  -- accepts { key, k1, ... kn }
  -- returns { num }
  function pack_unpacked_keys(inmap, outmap)
    local key = inmap.key
    if not key then
      kt.log("system", "pack_unpacked_keys() missing required 'key'")
      return kt.RVEINVALID
    else
      inmap.key = nil
    end
    local db = _select_db(inmap)

    local accum = {}
    local n = 0
    local v, xt
    for k, _ in pairs(inmap) do
      v, xt = db:get(k)
      if v ~= nil then
        accum[k] = cmsgpack.unpack(v)
        n = n + 1
      end
    end

    if not db:set(key, cmsgpack.pack(accum)) then
      kt.log('system', 'error setting packed key!')
      return kt.RVEINTERNAL
    end
    outmap.num = n
    return kt.RVSUCCESS
  end
end


-- Update or change the expire time for multiple keys.
-- accepts { key1: xt1, key2: xt2, ... }
-- returns { key1: old_xt1, key2: old_xt2, ... }
function touch_bulk(inmap, outmap)
  local db = _select_db(inmap)
  local keys = {}
  for key, _ in pairs(inmap) do
    table.insert(keys, key)
  end

  -- If there's nothing to do, return early.
  if #keys == 0 then
    return kt.RVSUCCESS
  end

  -- Visit each key specified by the user and update the expire time.
  local function visitor(key, value, xt)
    if not value then
      return kt.Visitor.NOP
    end
    outmap[key] = xt
    return value, inmap[key]
  end

  if not db:accept_bulk(keys, visitor) then
    kt.log('system', 'touch_bulk(): error calling accept_bulk()')
    return kt.RVEINTERNAL
  end
  return kt.RVSUCCESS
end


-- Increase the expire time for multiple keys.
-- accepts { key1: n1, key2: n2, ... }
-- returns { key1: xt1, key2: xt2, ... }
function touch_bulk_relative(inmap, outmap)
  local db = _select_db(inmap)
  local keys = {}
  for key, _ in pairs(inmap) do
    table.insert(keys, key)
  end

  -- If there's nothing to do, return early.
  if #keys == 0 then
    return kt.RVSUCCESS
  end

  -- Visit each key specified by the user and increase the expire time.
  local function visitor(key, value, xt)
    if not value then
      return kt.Visitor.NOP
    end
    local new_xt = xt + tonumber(inmap[key])
    outmap[key] = new_xt
    return value, -new_xt
  end

  if not db:accept_bulk(keys, visitor) then
    kt.log('system', 'touch_bulk_relative(): error calling accept_bulk()')
    return kt.RVEINTERNAL
  end
  return kt.RVSUCCESS
end


-- Read the expire time for a key.
-- accepts { key: key to read }
-- returns { xt: expire time }
function expire_time(inmap, outmap)
  local key = inmap.key
  if not key then
    kt.log("system", "expire_time() missing required 'key'")
    return kt.RVEINVALID
  end
  local db = _select_db(inmap)
  local value, xt = db:get(key)
  if xt then
    outmap['xt'] = xt
  end
  return kt.RVSUCCESS
end


-- Simple schedule implementation. Store timestamp + data (or any arbitrary
-- numeric value), and retrieve rows less than the timestamp.

-- Add item to schedule.
-- accepts { key, score, value, db }
-- returns { key }
function schedule_add(inmap, outmap)
  local db = _select_db(inmap)
  if not inmap.key then
    kt.log("system", "schedule_add() missing required 'key'")
    return kt.RVEINVALID
  elseif not inmap.value then
    kt.log("system", "schedule_add() missing required 'value'")
    return kt.RVEINVALID
  end
  local key = inmap.key
  local score = tonumber(inmap.score) or 0

  local next_id = db:increment_double(key, 1)
  if not next_id then
    kt.log("info", "unable to determine id when adding item to schedule!")
    return kt.RVELOGIC
  end
  -- local score_id = kt.pack("MM", score, next_id)
  local next_key = string.format("%s\t%012d%012d", key, score, next_id)
  if not db:add(next_key, inmap.value) then
    kt.log("system", "data for score/id '" .. score_id .. "' already exists.")
    return kt.RVELOGIC
  end
  outmap.key = next_key
  return kt.RVSUCCESS
end


-- Read (destructively) item(s) from the schedule.
-- accepts { key, score, n, db }
-- returns { 0: data0, 1: data1, ... }
function schedule_read(inmap, outmap)
  local db = _select_db(inmap)
  if not inmap.key then
    kt.log("system", "schedule_read() missing required 'key'")
    return kt.RVEINVALID
  end
  local key = inmap.key
  local max_score = tonumber(inmap.score) or 0xffffffff
  local n = tonumber(inmap.n or '-1')

  local cursor = db:cursor()
  local start_key = string.format("%s\t", key)
  local pattern = string.format("^%s\t", key)

  if not cursor:jump(start_key) then
    -- No data, we're done.
    cursor:disable()
    return kt.RVSUCCESS
  end

  local k, v, xt
  local num = 0
  local score_start = string.len(key) + 2  -- e.g. length + tab + 1.
  local score_end = score_start + 11  -- read 12 bytes.

  while n ~= 0 do
    -- Retrieve the key, value and xt from the cursor. If the cursor is
    -- invalidated then nil is returned.
    k, v, xt = cursor:get(false)
    if not k then break end

    -- If this is not a queue item key, we are done.
    if not k:match(pattern) then break end

    -- Extract the score from the key. If it is higher than the score provided
    -- by the caller, we are done.
    -- local score = kt.unpack("M", string.sub(k, score_start, score_end))[1]
    local score = tonumber(string.sub(k, score_start, score_end))
    if score > max_score then break end

    cursor:remove()  -- Implies step to the next record.
    outmap[num] = v
    num = num + 1
    n = n - 1
  end
  cursor:disable()
  return kt.RVSUCCESS
end


-- Test error code handling.
-- accepts { flag }
-- returns error code specified by flag.
function _error_code(inmap, outmap)
  local flag = tonumber(inmap.flag or 0)
  local error_map = {
    [0] = kt.RVSUCCESS,
    [1] = kt.RVENOIMPL,
    [2] = kt.RVEINVALID,
    [3] = kt.RVELOGIC,
    [4] = kt.RVEINTERNAL,
    [5] = kt.Error.NOREPOS,
    [6] = kt.Error.NOPERM,
    [7] = kt.Error.BROKEN,
    [8] = kt.Error.DUPREC,
    [9] = kt.Error.NOREC,
    [10] = kt.Error.SYSTEM,
    [11] = kt.Error.MISC}

  return error_map[flag]
end


ERROR_MAP = {
  [kt.Error.SUCCESS] = 'success',
  [kt.Error.NOIMPL] = 'noimpl',
  [kt.Error.INVALID] = 'invalid',
  [kt.Error.NOREPOS] = 'norepos',
  [kt.Error.NOPERM] = 'noperm',
  [kt.Error.BROKEN] = 'broken',
  [kt.Error.DUPREC] = 'duprec',
  [kt.Error.NOREC] = 'norec',
  [kt.Error.LOGIC] = 'logic',
  [kt.Error.SYSTEM] = 'system',
  [kt.Error.MISC] = 'misc'}


function get_error(inmap, outmap)
  local db = _select_db(inmap)
  local err = db:error()
  if err then
    local code = err:code()
    outmap['code'] = code
    outmap['message'] = ERROR_MAP[code]
  end
  return kt.RVSUCCESS
end


-- get luajit version.
function jit_version(inmap, outmap)
  outmap.version = jit.version or "<not present>"
  return kt.RVSUCCESS
end

if kt.thid == 0 then
  local version = jit and jit.version or "<not present>"
  kt.log("system", "luajit version: " .. version)
end
