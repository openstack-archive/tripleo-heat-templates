source 'https://rubygems.org'

group :development, :test do
  # puppetlabs_spec_helper 1.2.0 pulled in a gem with ruby >= 2.2 requirements
  # but CI has ruby 2.0.0.
  gem 'puppetlabs_spec_helper', '1.1.1', :require => 'false'

  gem 'puppet-lint', '~> 1.1'
  gem 'puppet-lint-absolute_classname-check'
  gem 'puppet-lint-absolute_template_path'
  gem 'puppet-lint-trailing_newline-check'

  # Puppet 4.x related lint checks
  gem 'puppet-lint-unquoted_string-check'
  gem 'puppet-lint-leading_zero-check'
  gem 'puppet-lint-variable_contains_upcase'
  gem 'puppet-lint-numericvariable'
end

if puppetversion = ENV['PUPPET_GEM_VERSION']
  gem 'puppet', puppetversion, :require => false
else
  gem 'puppet', :require => false
end

# vim:ft=ruby
