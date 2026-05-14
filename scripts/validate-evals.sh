#!/usr/bin/env bash
set -euo pipefail

ruby <<'RUBY'
require 'json'

files = Dir['skills/*/evals/evals.json'].sort
abort 'no eval files found' if files.empty?

total = 0
files.each do |file|
  data = JSON.parse(File.read(file))
  skill = data.fetch('skill_name')
  evals = data.fetch('evals')
  raise "#{file}: evals must be an array" unless evals.is_a?(Array)

  evals.each do |entry|
    total += 1
    %w[id prompt expected_output assertions].each do |key|
      raise "#{file}: eval #{entry.inspect} missing #{key}" unless entry.key?(key)
    end
    raise "#{file}: #{entry['id']} assertions must be non-empty" unless entry['assertions'].is_a?(Array) && !entry['assertions'].empty?
  end

  puts "#{skill}: #{evals.length} eval(s)"
end

puts "total: #{total} eval(s)"
RUBY
