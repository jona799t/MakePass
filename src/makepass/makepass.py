#!/usr/bin/env python3

import itertools
import re
import sys
import textwrap

try:
	from secrets import choice as random_choice
except ImportError:
	from random import SystemRandom
	random_choice = SystemRandom().choice
	del SystemRandom

from contextlib import closing
from math import log2
from pkg_resources import resource_stream

from autocommand import autocommand


def base_word_set(top_words):
	'''
	Get the initial set of words to create a password from
	'''
	# These files should have been installed by setup.py
	with closing(resource_stream('makepass', 'data/words.txt')) as file:
		yield from itertools.islice(
			(word.decode('utf8').strip() for word in file),
			top_words
		)


def constrain_word_length(words, min_len, max_len):
	'''
	Filter words from an iterable of words that are outside the inclusive
	length boundaries
	'''
	for word in words:
		if min_len <= len(word) <= max_len:
			yield word


def random_stream(things):
	'''
	Generate an infinite sequence of random things from a list of things.
	'''
	return map(random_choice, itertools.repeat(things))


def non_repeating(iterable):
	'''
	Given an iterable, yield only the unique elements
	'''
	seen = set()
	add = seen.add
	for thing in iterable:
		if thing not in seen:
			add(thing)
			yield thing


def gen_alpha_passwords(word_set, word_count):
	'''
	Generate an infinite sequence of alpha passwords, where each password is
	`word_count` concatenated words. Words are produced without replacement
	'''
	join = ''.join
	islice = itertools.islice
	words = random_stream(word_set)

	while True:
		yield join(islice(non_repeating(words), word_count))


def base_passwords(word_set, word_count, append_numeral, special_chars):
	'''
	Generate an infinite list of passwords
	'''
	gens = [gen_alpha_passwords(word_set, word_count)]
	if append_numeral:
		gens.append(random_stream('0123456789'))
	if special_chars:
		gens.append(random_stream(special_chars))

	return map(''.join, zip(*gens))


# We generate and pass around passwords as strings, for efficiency; this helper
# is provided to break a password back into its constituent parts. It returns
# [parts], (numeral or ""), (char or "")
def password_parts(password):
	# Assumes only ascii, which the current data set does fulfill.
	match = re.match(r'^((?:[A-Z][a-z]*)+)([0-9]?)([^a-zA-Z0-9]?)$', password)
	if match:
		word_parts = re.findall(r'[A-Z][a-z]*', match.group(1))
		number_part = match.group(2)
		char_part = match.group(3)
		return word_parts, number_part, char_part
	else:
		raise ValueError("Password doesn't match pattern generated by makepass")


def count_iterator(it):
	'''
	Count the length of an iterable. This consumes the iterator, if it doesn't
	have a len()
	'''
	try:
		return len(it)
	except TypeError:
		return sum(1 for _ in it)


def wordset_entropy(word_set_size, word_count):
	'''
	Get the entropy for selecting word_count words from a set of word_set_size,
	with replacement
	'''
	# We generate words without replacement, so for a word set size of N, the
	# entropy is log(N) + log(N - 1) + log(N - 2)...
	return sum(log2(word_set_size - n) for n in range(word_count))


def numeral_entropy(append_numeral):
	'''
	Get the entropy for appending a numeral (or not)
	'''
	return log2(10) if append_numeral else 0


def special_char_entropy(special_chars):
	'''
	Get the entropy for appending a specical character
	'''
	return log2(len(special_chars)) if special_chars else 0


def sampled_entropy(sample_size, success_size):
	'''
	Estimate the change in entropy given a sample of passwords from a set.

	Rationalle: Assume that we can produce passwords with a known entropy.
	However, not all of these passwords are at least 24 characters long. Rather
	than try to calculate the exact change in entropy, we estimate it by
	generating {sample_size} passwords, and seeing that {success_size} meet our
	constraints. We then assume that the ratio of these numbers is proportional
	to the overall ratio of possible_passwords to allowed_passwords. This
	allows us to do the following caluclation:

	original_entropy = log2(permutation_space)
	new_entropy = log2(permutation_space * ratio)
		= log2(permutation_space) + log2(ratio)
		= log2(permutation_space) + log2(success_size / sample_size)
		= log2(permutation_space) + log2(success_size) - log2(sample_size)
		= original_entropy + log2(success_size) - log2(sample_size)
	'''
	return log2(success_size) - log2(sample_size)


def estimate_entropy(
	word_set_size,
	word_count,
	append_numeral,
	special_chars,
	sample_size,
	success_size
):
	'''
	Perform a complete entropy estimate using wordset_entropy, numeral_entropy,
	sampled_entropy
	'''
	return (
		wordset_entropy(word_set_size, word_count) +
		numeral_entropy(append_numeral) +
		special_char_entropy(special_chars) +
		sampled_entropy(sample_size, success_size)
	)


def errfmt(fmt, *args, **kwargs):
	'''
	Given a format string, .format() it with the args and kwargs, text wrap it
	to 70 columns, and write it to stderr.
	'''
	return print(textwrap.fill(
		fmt.format(*args, **kwargs)
	), file=sys.stderr)


def lengthfmt(min_length, max_length):
	'''
	Create a human-readable length string suitible for use in
	"length of {len} characters"
	'''
	if min_length == max_length:
		return "exactly {}".format(min_length)
	elif min_length == 1:
		if max_length == float('inf'):
			return "any number of"
		else:
			return "up to {}".format(max_length)
	else:
		if max_length == float('inf'):
			return "at least {}".format(min_length)
		else:
			return "between {} and {}".format(min_length, max_length)


@autocommand(__name__)
def main(
	word_count: 'Number of words in the password (defaults to %(default)s)' =4,
	min_length: (
		'Minimum character length in the password (defaults to 24, or '
		'MAX_LENGTH)', int) =None,
	max_length: ('Maximum character length in the password (defaults to unlimited)', int) =None,
	append_char: "Append a random special character to the password" =False,
	special_set:
		"When using --append_char, this is the set of special characters to "
		"select from. Defaults to [%(default)s]" ="-_()/.,?!;:",
	no_append_numeral: "Don't append random 0-9 numeral to the password" =False,
	min_word: 'Minimum length of each individual word in the password (defaults to %(default)s)' =4,
	max_word: 'Maximum length of each individual word in the password (defaults to %(default)s)' =8,
	entropy_estimate: "Print an entropy estimate to stderr" =False,
	verbose: 'Print verbose entropy calculation details to stderr' =False,
	count: 'Print the character length of the password to stderr' =False,
	sample_size:
		"Number of internal passwords to produce. Used for entropy estimates, "
		"and as the number of attempts before giving up" =10000,
	top_words: "Use the top TOP_WORDS most common words from the word list. "
		"Defaults to 20,000. Using a smaller word list will make your "
		"password less secure, but possibly easier to remember" =20000
):
	'''
	%(prog)s is a password generator inspired by https://xkcd.com/936/. It
	generates simple, memorable, secure passwords by combining common english
	words. All parameters are optional; under the default settings it generates
	a password with an entropy of roughly 57.5 bits and an average length of
	27 characters.
	'''
	if min_word > max_word:
		return "min_word must be less than or equal to max_word"

	if min_length is None and max_length is None:
		min_length = 24
		max_length = float('inf')
	elif max_length and not min_length:
		min_length = max_length
	elif min_length and not max_length:
		max_length = float('inf')

	if min_length > max_length:
		return "min_length must be less than or equal to max_length"

	min_length = max(1, min_length)
	min_word = max(1, min_word)

	min_possible_size = (
		(min_word * word_count) +
		(0 if no_append_numeral else 1) +
		(1 if append_char else 0)
	)
	max_possible_size = (
		(max_word * word_count) +
		(0 if no_append_numeral else 1) +
		(1 if append_char else 0)
	)

	if min_possible_size > max_length:
		return (
			"Impossible constraints: minumum possible size ({size}) greater "
			"than maximum allowed password length ({allowed})".format(
				size=min_possible_size,
				allowed=max_length
			)
		)
	elif max_possible_size < min_length:
		return (
			"Impossible constraints: maximum possible size ({size}) less than "
			"minimum allowed password length ({allowed})".format(
				size=max_possible_size,
				allowed=min_length
			)
		)

	word_set = tuple(
		constrain_word_length(base_word_set(top_words), min_word, max_word)
	)

	word_set_size = len(word_set)

	special_set = special_set if append_char else ''

	invalid_special_char = re.search(r'[a-zA-Z\d\s]', special_set)
	if invalid_special_char:
		return (
			"Invalid special character {char} in special character set. "
			"Special characters should not be alpha, numeric, or whitespace."
		)

	if log2(word_set_size) > min_word * log2(26):
		errfmt(
			"Warning: the entropy of brute forcing a short word (that is, "
			"brute forcing it as a random string of ascii) is less than "
			"that of selecting one from the random set; the password may be "
			"less secure than the entropy estimate indicates, especially if "
			"using a small max_word")

	# Produce an infinite set of passwords, using the constraints
	passwords = base_passwords(
		word_set=word_set,
		word_count=word_count,
		append_numeral=not no_append_numeral,
		special_chars=special_set
	)

	# Sample the passwords
	passwords = itertools.islice(passwords, sample_size)

	# Filter the sampled set by word length
	passwords = constrain_word_length(passwords, min_length, max_length)

	try:
		password = next(passwords)
	except StopIteration:
		return "Couldn't generate password matching constraints"

	if entropy_estimate or verbose:
		success_size = count_iterator(passwords) + 1

		entropy = estimate_entropy(
			word_set_size=word_set_size,
			word_count=word_count,
			append_numeral=not no_append_numeral,
			special_chars=special_set,
			sample_size=sample_size,
			success_size=success_size
		)

		if verbose:
			errfmt(
				"Generated a password of {word_count} non-repeating "
				"words, from a set of {word_set_size} common english words of "
				"{lenfmt} letters: {bits:.4f} bits of entropy.",

				word_count=word_count,
				word_set_size=word_set_size,
				lenfmt=lengthfmt(min_word, max_word),
				bits=wordset_entropy(word_set_size, word_count),
			)

			if not no_append_numeral:
				errfmt(
					"A random numeral in the range 0-9 was appended, for an "
					"additional {bits:.4f} bits of entropy.",
					bits=numeral_entropy(True),
				)

			if special_set:
				if len(special_set) == 1:
					errfmt(
						"The special character {special_char} was appended. "
						"This added no entropy.",
						special_char=special_set
					)
				else:
					errfmt(
						"A random character from the set [{special_chars}] was "
						"appended, for an additional {bits:.4f} bits of "
						"entropy.",
						special_chars=special_set,
						bits=special_char_entropy(special_set)
					)

			if success_size != sample_size:
				errfmt(
					"{sample_size} sample passwords were generated, but only "
					"{success_size} passwords had a length of {lenfmt} "
					"letters. The entropy estimate was adjusted "
					"accordingly by {bits:.4f} bits.",

					sample_size=sample_size,
					success_size=success_size,
					min_length=min_length,
					lenfmt=lengthfmt(min_length, max_length),
					bits=sampled_entropy(sample_size, success_size),
				)

		errfmt("Estimated total password entropy: {:.2f} bits", entropy)

	if verbose or count:
		errfmt("The password is {len} characters long", len=len(password))

	print(password)
